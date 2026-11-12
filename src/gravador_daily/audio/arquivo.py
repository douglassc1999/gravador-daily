"""Fonte de áudio a partir de arquivo (WAV/MP3/M4A/MP4…) via ffmpeg.

Usada em testes no Linux e também pelo recurso "Transcrever arquivo de áudio…".
Quando ``acelerado=True`` não dorme entre blocos (útil para testes rápidos).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from ..mixagem import TAXA_PADRAO
from .base import ErroFonteAudio, FonteAudio

#: bloco padrão entregue pela fonte (0,5 s)
BLOCO_S = 0.5

#: caminho de desenvolvimento conhecido no Linux do Douglas
FFMPEG_DEV = "/home/douglas/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg"


def caminho_ffmpeg() -> str:
    """Localiza um ffmpeg: variável de ambiente → embutido → sistema → dev."""
    env = os.environ.get("GRAVADOR_FFMPEG")
    if env and Path(env).exists():
        return env

    # Embutido ao lado do executável (PyInstaller copia o ffmpeg para cá).
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve()
    for nome in ("ffmpeg.exe", "ffmpeg"):
        cand = base / nome
        if cand.exists():
            return str(cand)

    try:  # imageio-ffmpeg traz um binário pronto
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    sistema = shutil.which("ffmpeg")
    if sistema:
        return sistema
    if Path(FFMPEG_DEV).exists():
        return FFMPEG_DEV
    raise ErroFonteAudio(
        "ffmpeg não encontrado. Instale o ffmpeg ou defina a variável GRAVADOR_FFMPEG."
    )


class FonteArquivo(FonteAudio):
    """Decodifica um arquivo de áudio em blocos de 16 kHz mono float32."""

    def __init__(
        self,
        caminho: str | Path,
        acelerado: bool = False,
        taxa: int = TAXA_PADRAO,
        bloco_s: float = BLOCO_S,
    ) -> None:
        super().__init__()
        self.caminho = Path(caminho)
        self.acelerado = acelerado
        self.taxa = taxa
        self._tam_bloco = int(taxa * bloco_s)
        self._proc: subprocess.Popen | None = None
        self._buffer = b""

    def abrir(self) -> None:
        if not self.caminho.exists():
            raise ErroFonteAudio(f"Arquivo de áudio não encontrado: {self.caminho}")
        ffmpeg = caminho_ffmpeg()
        cmd = [
            ffmpeg,
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(self.caminho),
            "-vn",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(self.taxa),
            "pipe:1",
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def _ler_bytes(self, n_bytes: int) -> bytes:
        assert self._proc is not None and self._proc.stdout is not None
        partes = []
        restante = n_bytes
        while restante > 0:
            dados = self._proc.stdout.read(restante)
            if not dados:
                break
            partes.append(dados)
            restante -= len(dados)
        return b"".join(partes)

    def ler_bloco(self) -> np.ndarray | None:
        if self._proc is None:
            self.abrir()
        n_bytes = self._tam_bloco * 4  # float32
        inicio = time.monotonic()
        dados = self._buffer + self._ler_bytes(n_bytes - len(self._buffer))
        self._buffer = b""
        if not dados:
            return None
        # Guarda sobra incompleta (menos que um float) para o próximo bloco.
        completa = len(dados) - (len(dados) % 4)
        self._buffer = dados[completa:]
        bloco = np.frombuffer(dados[:completa], dtype=np.float32).copy()
        if bloco.size == 0:
            return None
        if not self.acelerado:
            alvo = inicio + self._tam_bloco / self.taxa
            espera = alvo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
        self.niveis["arquivo"] = float(np.sqrt(np.mean(np.square(bloco))))
        return bloco

    def parar(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdout and self._proc.stdout.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    @property
    def descricao(self) -> str:
        return f"Arquivo ({self.caminho.name})"
