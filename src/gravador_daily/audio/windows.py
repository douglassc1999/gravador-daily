"""Captura de áudio no Windows: microfone padrão + loopback WASAPI.

Usa ``PyAudioWPatch`` (que expõe o loopback do WASAPI, indisponível no
``PyAudio`` clássico). Cada dispositivo roda numa thread própria lendo em
streaming, e o áudio é convertido para float32 mono 16 kHz antes de ser
misturado. Se um dos dispositivos faltar, seguimos com o outro e registramos um
aviso em PT-BR (mostrado na janela).

AVISO: este módulo é *Windows-only* e foi escrito sem execução real neste
ambiente Linux — a captura de loopback precisa ser validada no Windows.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

import numpy as np

from ..mixagem import TAXA_PADRAO, misturar, para_mono, resample, rms
from .base import ErroFonteAudio, FonteAudio

#: tamanho de cada quadro entregue ao app
BLOCO_S = 0.5


class _LeitorThread(threading.Thread):
    """Lê um único stream do PyAudio e publica blocos 16 kHz mono numa fila."""

    def __init__(
        self,
        pa: Any,
        taxa: int,
        canais: int,
        nome: str,
        fila: "queue.Queue[tuple[str, np.ndarray]]",
        niveis: dict[str, float] | None = None,
        dispositivo: int | None = None,
        frames_por_buffer: int | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"leitor-{nome}")
        self.pa = pa
        self.taxa = taxa
        self.canais = canais
        self.nome = nome
        self.fila = fila
        self.niveis = niveis if niveis is not None else {}
        self.dispositivo = dispositivo
        self.frames_por_buffer = frames_por_buffer or int(taxa * BLOCO_S)
        self._stream = None
        self._parar = threading.Event()
        self.erro: Exception | None = None

    def _callback(self, in_data, frame_count, time_info, status):  # noqa: ANN001
        try:
            arr = np.frombuffer(in_data, dtype=np.float32)
            if self.canais > 1:
                arr = arr.reshape(-1, self.canais)
            mono = para_mono(arr)
            bloco = resample(mono, self.taxa, TAXA_PADRAO)
            self.niveis[self.nome] = rms(bloco)
            self.fila.put((self.nome, bloco))
        except Exception as exc:  # pragma: no cover - proteção do callback
            self.erro = exc
        import pyaudiowpatch as pyaudio  # noqa: F401

        return (None, pyaudio.paContinue)

    def run(self) -> None:  # pragma: no cover - requer hardware Windows
        import pyaudiowpatch as pyaudio

        try:
            kwargs: dict[str, Any] = dict(
                format=pyaudio.paFloat32,
                channels=self.canais,
                rate=self.taxa,
                input=True,
                frames_per_buffer=self.frames_por_buffer,
                stream_callback=self._callback,
            )
            if self.dispositivo is not None:
                kwargs["input_device_index"] = self.dispositivo
            self._stream = self.pa.open(**kwargs)
            self._stream.start_stream()
            while not self._parar.is_set() and self._stream.is_active():
                self._parar.wait(0.2)
        except Exception as exc:
            self.erro = exc
        finally:
            self._fechar()

    def _fechar(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def parar(self) -> None:
        self._parar.set()
        self._fechar()


class FonteWindows(FonteAudio):
    """Mic + loopback do sistema, misturados em mono 16 kHz float32."""

    def __init__(self, taxa: int = TAXA_PADRAO) -> None:
        super().__init__()
        self.taxa = taxa
        self._pa = None
        self._leitores: list[_LeitorThread] = []
        self._fila: "queue.Queue[tuple[str, np.ndarray]]" = queue.Queue()
        self._restantes: set[str] = set()
        self._acumuladores: dict[str, list[np.ndarray]] = {}
        self._tam_bloco = int(taxa * BLOCO_S)
        self.ligado_microfone = False
        self.ligado_loopback = False

    # -- descoberta de dispositivos --------------------------------------- #
    def _abrir_microfone(self) -> None:
        try:
            info = self._pa.get_default_input_device_info()
        except Exception:
            self._adicionar_aviso(
                "Microfone não encontrado: gravando apenas o som do computador."
            )
            return
        taxa = int(info["defaultSampleRate"])
        canais = int(info.get("maxInputChannels") or 1) or 1
        canais = 1 if canais < 1 else canais
        leitor = _LeitorThread(
            self._pa,
            taxa,
            canais,
            "mic",
            self._fila,
            niveis=self.niveis,
            dispositivo=int(info["index"]),
            frames_por_buffer=int(taxa * BLOCO_S),
        )
        self._leitores.append(leitor)
        self.ligado_microfone = True

    def _abrir_loopback(self) -> None:
        try:
            info = self._pa.get_default_wasapi_loopback()
        except Exception:
            self._adicionar_aviso(
                "Som do computador (loopback WASAPI) indisponível: gravando apenas o microfone."
            )
            return
        taxa = int(info["defaultSampleRate"])
        canais = int(info.get("maxInputChannels") or 2) or 2
        leitor = _LeitorThread(
            self._pa,
            taxa,
            max(1, canais),
            "loopback",
            self._fila,
            niveis=self.niveis,
            dispositivo=int(info["index"]),
            frames_por_buffer=int(taxa * BLOCO_S),
        )
        self._leitores.append(leitor)
        self.ligado_loopback = True

    # -- ciclo de vida ----------------------------------------------------- #
    def abrir(self) -> None:  # pragma: no cover - requer Windows + hardware
        try:
            import pyaudiowpatch as pyaudio
        except Exception as exc:
            raise ErroFonteAudio(
                "PyAudioWPatch não está instalado. No Windows reinstale o aplicativo "
                "(a captura de som do sistema depende dele)."
            ) from exc

        self._pa = pyaudio.PyAudio()
        self._abrir_microfone()
        self._abrir_loopback()

        if not self._leitores:
            raise ErroFonteAudio(
                "Não foi possível acessar nenhum dispositivo de áudio "
                "(nem microfone, nem som do computador)."
            )

        self._restantes = {leitor.nome for leitor in self._leitores}
        for leitor in self._leitores:
            self._acumuladores[leitor.nome] = []
            leitor.start()

        for aviso in self.avisos:
            pass  # os avisos já ficaram registrados em self._avisos

    def ler_bloco(self) -> np.ndarray | None:  # pragma: no cover - hardware
        if self._pa is None:
            self.abrir()

        # Acumula blocos de cada faixa até completar BLOCO_S.
        while self._restantes:
            restante = min(
                (self._tam_bloco - sum(b.size for b in self._acumuladores[n]))
                for n in self._restantes
            )
            if restante <= 0:
                break
            try:
                nome, bloco = self._fila.get(timeout=2.0)
            except queue.Empty:
                # Um leitor pode ter morrido; remove faixas sem atividade.
                mortos = [l.nome for l in self._leitores if l.erro is not None]
                for nome_morto in mortos:
                    self._restantes.discard(nome_morto)
                    self._adicionar_aviso(
                        f"Faixa '{nome_morto}' parou de responder: seguindo sem ela."
                    )
                if not self._restantes:
                    return None
                continue
            if nome in self._acumuladores:
                self._acumuladores[nome].append(bloco)

        faixas = []
        for nome in list(self._acumuladores):
            if nome not in self._restantes:
                continue
            partes = self._acumuladores[nome]
            if not partes:
                continue
            if len(partes) == 1:
                faixas.append(partes[0])
            else:
                faixas.append(np.concatenate(partes).astype(np.float32))
            self._acumuladores[nome] = []
        if not faixas:
            return None
        return misturar(faixas)

    def parar(self) -> None:  # pragma: no cover - hardware
        for leitor in self._leitores:
            leitor.parar()
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    @property
    def descricao(self) -> str:
        return "Microfone + som do computador (Windows)"
