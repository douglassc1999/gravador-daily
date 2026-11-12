"""Sessão de gravação: junta a fonte de áudio, o WAV bruto e a transcrição.

Este módulo não conhece a plataforma: recebe uma :class:`~gravador_daily.audio.base.FonteAudio`
pronta. A captura roda numa thread própria, alimenta um arquivo WAV incremental e
a transcrição incremental (fila + thread), de modo que nenhum áudio se perca.
"""

from __future__ import annotations

import queue
import threading
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from . import saida as mod_saida
from .audio.base import ErroFonteAudio, FonteAudio
from .config import Config
from .mixagem import TAXA_PADRAO, float_para_int16, rms
from .transcritor import (
    MotorTranscricao,
    Segmento,
    TranscricaoIncremental,
    transcrever_wav,
)


@dataclass
class ResultadoGravacao:
    caminho_txt: Path
    caminho_srt: Path
    caminho_wav: Path | None
    segmentos: list[Segmento] = field(default_factory=list)
    duracao_s: float = 0.0


class SessaoGravacao:
    """Orquestra uma gravação do início ao fim (menos a interface)."""

    def __init__(
        self,
        fonte: FonteAudio,
        motor: MotorTranscricao,
        cfg: Config,
        nome: str,
        pasta_saida: Path,
        ao_status: Callable[[str], None] | None = None,
        ao_nivel: Callable[[dict[str, float]], None] | None = None,
        ao_progresso: Callable[[float], None] | None = None,
        ao_segmento: Callable[[Segmento], None] | None = None,
    ) -> None:
        self.fonte = fonte
        self.motor = motor
        self.cfg = cfg
        self.nome = nome
        self.pasta_saida = Path(pasta_saida)
        self.ao_status = ao_status or (lambda _m: None)
        self.ao_nivel = ao_nivel or (lambda _n: None)
        self.ao_progresso = ao_progresso or (lambda _p: None)
        self.ao_segmento = ao_segmento or (lambda _s: None)

        self.inicio = datetime.now()
        self.base = mod_saida.nome_base(self.inicio, nome)
        self.caminho_wav = self.pasta_saida / f"{self.base}.wav"

        self._incremental = TranscricaoIncremental(
            motor, ao_progresso=self.ao_progresso, ao_segmento=self.ao_segmento
        )
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._fim_captura = threading.Event()
        self._wav: wave.Wave_write | None = None
        self._duracao = 0.0
        self._erro: Exception | None = None

    # -- ciclo de vida ----------------------------------------------------- #
    def iniciar(self) -> None:
        self.pasta_saida.mkdir(parents=True, exist_ok=True)
        try:
            self.fonte.abrir()
        except ErroFonteAudio as exc:
            raise
        self.ao_status(f"Gravando — {self.fonte.descricao}")
        for aviso in self.fonte.avisos:
            self.ao_status(aviso)

        # Abre o WAV (mantido mesmo se o app fechar no meio).
        self._wav = wave.open(str(self.caminho_wav), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(TAXA_PADRAO)

        self._incremental.iniciar()
        self._parar.clear()
        self._thread = threading.Thread(target=self._capturar, daemon=True, name="captura")
        self._thread.start()

    def _capturar(self) -> None:
        try:
            while not self._parar.is_set():
                bloco = self.fonte.ler_bloco()
                if bloco is None:
                    break
                if bloco.size == 0:
                    continue
                if self._wav is not None:
                    self._wav.writeframes(float_para_int16(bloco).tobytes())
                self._duracao += bloco.size / TAXA_PADRAO
                niveis = getattr(self.fonte, "niveis", None) or {}
                if niveis:
                    self.ao_nivel({k: min(1.0, v * 6.0) for k, v in niveis.items()})
                else:
                    self.ao_nivel({"audio": min(1.0, rms(bloco) * 6.0)})
                self._incremental.alimentar(bloco)
        except Exception as exc:  # pragma: no cover - proteção da thread
            self._erro = exc
        finally:
            self._fim_captura.set()
            self.ao_nivel({})

    def aguardar_captura(self, timeout: float = 30.0) -> bool:
        """Espera o fim natural da captura (EOF da fonte). Usado em testes."""
        return self._fim_captura.wait(timeout)

    @property
    def duracao(self) -> float:
        return self._duracao

    @property
    def progresso(self) -> float:
        return self._incremental.progresso

    @property
    def avisos(self) -> list[str]:
        return self.fonte.avisos

    # -- finalização ------------------------------------------------------- #
    def parar(self) -> ResultadoGravacao:
        """Para a captura, transcreve o restante e grava .txt/.srt."""
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
        if self._wav is not None:
            self._wav.close()
            self._wav = None
        try:
            self.fonte.parar()
        except Exception:
            pass
        if self._erro is not None:
            raise self._erro

        segmentos = self._incremental.finalizar()
        caminho_txt, caminho_srt = mod_saida.salvar_saidas(
            self.pasta_saida,
            self.base,
            segmentos,
            self.nome,
            self.inicio,
            self._duracao,
        )
        caminho_wav: Path | None = self.caminho_wav
        if not self.cfg.manter_audio:
            try:
                self.caminho_wav.unlink(missing_ok=True)
            except Exception:
                pass
            caminho_wav = None
        return ResultadoGravacao(
            caminho_txt=caminho_txt,
            caminho_srt=caminho_srt,
            caminho_wav=caminho_wav,
            segmentos=segmentos,
            duracao_s=self._duracao,
        )


# --------------------------------------------------------------------------- #
# Recuperação de gravação interrompida
# --------------------------------------------------------------------------- #
def gravacoes_pendentes(pasta: Path) -> list[Path]:
    """WAVs na pasta de saída que ainda não têm .txt correspondente."""
    pasta = Path(pasta)
    if not pasta.exists():
        return []
    pendentes = []
    for wav in sorted(pasta.glob("*.wav")):
        if not (pasta / f"{wav.stem}.txt").exists():
            pendentes.append(wav)
    return pendentes


def reprocessar(
    caminho_wav: str | Path,
    motor: MotorTranscricao,
    cfg: Config,
    ao_progresso: Callable[[float], None] | None = None,
) -> ResultadoGravacao:
    """Transcreve um WAV existente (gravação não transcrita) e gera txt/srt."""
    caminho_wav = Path(caminho_wav)
    nome = caminho_wav.stem.split("_", 2)[-1] if "_" in caminho_wav.stem else cfg.nome_padrao
    segmentos = transcrever_wav(caminho_wav, motor, ao_progresso=ao_progresso)
    duracao = 0.0
    if segmentos:
        duracao = segmentos[-1].fim
    inicio = datetime.fromtimestamp(caminho_wav.stat().st_mtime)
    caminho_txt, caminho_srt = mod_saida.salvar_saidas(
        caminho_wav.parent,
        caminho_wav.stem,
        segmentos,
        nome,
        inicio,
        duracao,
    )
    return ResultadoGravacao(
        caminho_txt=caminho_txt,
        caminho_srt=caminho_srt,
        caminho_wav=caminho_wav,
        segmentos=segmentos,
        duracao_s=duracao,
    )
