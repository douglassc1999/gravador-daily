"""Transcrição com faster-whisper + controle incremental com corte em silêncio.

Duas peças independentes:

* :func:`encontrar_corte` / :func:`planejar_cortes` — decidem, por energia
  (VAD simples), onde cortar o áudio acumulado no silêncio mais próximo.
* :class:`TranscricaoIncremental` — acumula áudio que chega da captura, enfileira
  trechos para uma thread de trabalho e mantém os offsets de tempo absolutos.

O motor de transcrição é injetável (:class:`MotorTranscricao`), então os testes
usam um motor falso e não precisam do modelo Whisper.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .mixagem import TAXA_PADRAO, concatenar, rms

PROMPT_PADRAO = "Reunião diária de equipe de desenvolvimento de software."


# --------------------------------------------------------------------------- #
# Segmentos
# --------------------------------------------------------------------------- #
@dataclass
class Segmento:
    inicio: float
    fim: float
    texto: str


# --------------------------------------------------------------------------- #
# Corte em silêncio
# --------------------------------------------------------------------------- #
def _energias(audio: np.ndarray, janela: int) -> np.ndarray:
    """RMS por janelas consecutivas (expresso em amostras de ``janela``)."""
    n = audio.size // janela
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    recorte = audio[: n * janela].reshape(n, janela)
    return np.sqrt(np.mean(np.square(recorte), axis=1)).astype(np.float32)


def encontrar_corte(
    audio: np.ndarray,
    alvo: int,
    janela: int = int(0.3 * TAXA_PADRAO),
    busca: int = int(10.0 * TAXA_PADRAO),
    minimo: int = 0,
    limite: int | None = None,
) -> int:
    """Escolhe o índice de corte (amostras) com menor energia perto de ``alvo``.

    Procura dentro de ``[alvo - busca, alvo + busca]`` a janela de menor RMS e
    devolve o centro dela. Nunca devolve menos que ``minimo``.
    """
    limite = audio.size if limite is None else limite
    if audio.size == 0:
        return 0
    inicio = max(0, alvo - busca)
    fim = min(limite, alvo + busca)
    if fim - inicio < janela:
        return max(minimo, min(alvo, limite))

    energias = _energias(audio[inicio:fim], janela)
    if energias.size == 0:
        return max(minimo, min(alvo, limite))
    idx = int(np.argmin(energias))
    centro = inicio + idx * janela + janela // 2
    return int(max(minimo, min(centro, limite)))


def planejar_cortes(
    audio: np.ndarray,
    alvo_s: float = 45.0,
    taxa: int = TAXA_PADRAO,
    busca_s: float = 10.0,
    min_s: float = 5.0,
) -> list[tuple[int, int]]:
    """Devolve a lista de trechos ``(inicio, fim)`` cobrindo o áudio.

    Cada trecho tem ~``alvo_s`` segundos, com o corte ajustado ao silêncio mais
    próximo. O último trecho pode ser mais curto.
    """
    alvo = int(alvo_s * taxa)
    busca = int(busca_s * taxa)
    minimo_trecho = int(min_s * taxa)
    trechos: list[tuple[int, int]] = []
    pos = 0
    while audio.size - pos > 0:
        restante = audio.size - pos
        if restante <= alvo:
            trechos.append((pos, audio.size))
            break
        corte = encontrar_corte(
            audio, pos + alvo, busca=busca, minimo=pos + minimo_trecho
        )
        trechos.append((pos, corte))
        pos = corte
    return trechos


# --------------------------------------------------------------------------- #
# Motores de transcrição
# --------------------------------------------------------------------------- #
class ErroModeloAusente(RuntimeError):
    """Modelo Whisper não encontrado (mensagem amigável em PT-BR)."""


class MotorTranscricao:
    """Contrato do motor: recebe áudio 16 kHz e devolve segmentos absolutos."""

    def transcrever(self, audio: np.ndarray, offset: float) -> list[Segmento]:
        raise NotImplementedError


class WhisperMotor(MotorTranscricao):
    """faster-whisper small, CPU int8, idioma pt."""

    def __init__(
        self,
        modelo_dir: str | Path,
        idioma: str = "pt",
        cpu_threads: int | None = None,
        prompt: str = PROMPT_PADRAO,
        compute_type: str = "int8",
    ) -> None:
        self.modelo_dir = Path(modelo_dir)
        self.idioma = idioma
        self.cpu_threads = cpu_threads
        self.prompt = prompt
        self.compute_type = compute_type
        self._modelo = None

    # -- carregamento ------------------------------------------------------ #
    def carregar(self) -> None:
        if self._modelo is not None:
            return
        if not self.modelo_dir.exists():
            raise ErroModeloAusente(
                "Modelo de transcrição não encontrado em "
                f"'{self.modelo_dir}'.\n\n"
                "Se você está usando o aplicativo instalado, os arquivos podem ter "
                "sido movidos ou apagados: baixe novamente o GravadorDaily.\n"
                "Se você é desenvolvedor, rode: python scripts/baixar_modelo.py"
            )
        from faster_whisper import WhisperModel

        opcoes = dict(device="cpu", compute_type=self.compute_type)
        if self.cpu_threads:
            opcoes["cpu_threads"] = self.cpu_threads
        self._modelo = WhisperModel(str(self.modelo_dir), **opcoes)

    def transcrever(self, audio: np.ndarray, offset: float) -> list[Segmento]:
        self.carregar()
        if audio.size == 0:
            return []
        segmentos, _info = self._modelo.transcribe(
            audio,
            language=self.idioma,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
            word_timestamps=False,
        )
        saida: list[Segmento] = []
        for seg in segmentos:
            texto = (seg.text or "").strip()
            if not texto:
                continue
            saida.append(
                Segmento(offset + float(seg.start), offset + float(seg.end), texto)
            )
        return saida


# --------------------------------------------------------------------------- #
# Controle incremental
# --------------------------------------------------------------------------- #
class TranscricaoIncremental:
    """Acumula áudio, corta em silêncio e transcreve em uma thread de trabalho.

    Uso::

        inc = TranscricaoIncremental(motor)
        inc.iniciar()
        inc.alimentar(bloco)      # pode ser chamado de qualquer thread
        segmentos = inc.finalizar()
    """

    def __init__(
        self,
        motor: MotorTranscricao,
        alvo_s: float = 45.0,
        busca_s: float = 10.0,
        min_s: float = 5.0,
        taxa: int = TAXA_PADRAO,
        ao_progresso: Callable[[float], None] | None = None,
        ao_segmento: Callable[[Segmento], None] | None = None,
    ) -> None:
        self.motor = motor
        self.alvo_s = alvo_s
        self.busca_s = busca_s
        self.min_s = min_s
        self.taxa = taxa
        self.ao_progresso = ao_progresso
        self.ao_segmento = ao_segmento

        self._lock = threading.Lock()
        self._buffer = np.zeros(0, dtype=np.float32)
        self._offset_buffer = 0.0  # tempo (s) do início do buffer atual
        self._duracao_enviada = 0.0
        self._duracao_processada = 0.0
        self._segmentos: list[Segmento] = []

        self._fila: "queue.Queue[np.ndarray | None]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._erro: Exception | None = None

    # -- thread ------------------------------------------------------------ #
    def iniciar(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._trabalhar, daemon=True, name="transcritor")
        self._thread.start()

    def _trabalhar(self) -> None:
        while True:
            item = self._fila.get()
            try:
                if item is None:
                    return
                offset, trecho = item
                for seg in self.motor.transcrever(trecho, offset):
                    self._segmentos.append(seg)
                    if self.ao_segmento:
                        self.ao_segmento(seg)
                with self._lock:
                    self._duracao_processada += trecho.size / self.taxa
                self._notificar_progresso()
            except Exception as exc:  # pragma: no cover - caminho de erro
                self._erro = exc
            finally:
                self._fila.task_done()

    def _notificar_progresso(self) -> None:
        if not self.ao_progresso:
            return
        with self._lock:
            total = self._duracao_enviada
            proc = self._duracao_processada
        fracao = 1.0 if total <= 0 else min(1.0, proc / total)
        self.ao_progresso(fracao)

    # -- alimentação ------------------------------------------------------- #
    def alimentar(self, bloco: np.ndarray) -> None:
        if bloco is None or bloco.size == 0:
            return
        bloco = np.asarray(bloco, dtype=np.float32).reshape(-1)
        with self._lock:
            precisa = int(self.alvo_s * self.taxa)
            if self._buffer.size == 0:
                self._offset_buffer = self._duracao_enviada
            self._buffer = concatenar([self._buffer, bloco])
            self._duracao_enviada += bloco.size / self.taxa
            if self._buffer.size >= precisa + int(self.busca_s * self.taxa):
                corte = encontrar_corte(
                    self._buffer,
                    precisa,
                    busca=int(self.busca_s * self.taxa),
                    minimo=int(self.min_s * self.taxa),
                )
                trecho = self._buffer[:corte].copy()
                self._buffer = self._buffer[corte:]
                self._offset_buffer += corte / self.taxa
            else:
                trecho = None
        if trecho is not None and trecho.size:
            self._fila.put((self._offset_buffer - trecho.size / self.taxa, trecho))

    # -- finalização ------------------------------------------------------- #
    def finalizar(self) -> list[Segmento]:
        """Transcreve o restante, aguarda a fila e devolve os segmentos."""
        with self._lock:
            trecho = self._buffer.copy()
            offset = self._offset_buffer
            self._buffer = np.zeros(0, dtype=np.float32)
        if trecho.size:
            self._fila.put((offset, trecho))
        self._fila.join()
        if self._thread is not None:
            self._fila.put(None)
            self._thread.join(timeout=30)
            self._thread = None
        self._notificar_progresso()
        if self._erro is not None:
            raise self._erro
        return sorted(self._segmentos, key=lambda s: s.inicio)

    # -- consultas --------------------------------------------------------- #
    @property
    def segmentos(self) -> list[Segmento]:
        return sorted(self._segmentos, key=lambda s: s.inicio)

    @property
    def progresso(self) -> float:
        with self._lock:
            total = self._duracao_enviada
            proc = self._duracao_processada
        return 1.0 if total <= 0 else min(1.0, proc / total)

    @property
    def duracao_enviada(self) -> float:
        with self._lock:
            return self._duracao_enviada


# --------------------------------------------------------------------------- #
# Conveniência: transcrever uma gravação WAV inteira
# --------------------------------------------------------------------------- #
def transcrever_wav(
    caminho_wav: str | Path,
    motor: MotorTranscricao,
    alvo_s: float = 45.0,
    ao_progresso: Callable[[float], None] | None = None,
) -> list[Segmento]:
    """Reprocessa um WAV já gravado (recuperação de gravação interrompida)."""
    from .mixagem import ler_wav_16k

    audio = ler_wav_16k(caminho_wav, TAXA_PADRAO)
    inc = TranscricaoIncremental(motor, alvo_s=alvo_s, ao_progresso=ao_progresso)
    inc.iniciar()
    blocos = planejar_cortes(audio, alvo_s=alvo_s)
    for inicio, fim in blocos:
        inc.alimentar(audio[inicio:fim])
    return inc.finalizar()


def rms_bloco(audio: np.ndarray) -> float:  # reexport para conveniência da UI
    return rms(audio)
