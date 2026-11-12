"""Interface comum das fontes de áudio e a fábrica ``criar_fonte``.

Contrato: uma fonte entrega blocos de ``float32`` mono a 16 kHz via
``ler_bloco()``. Devolver ``None`` significa fim da fonte (EOF). A fonte deve
ser thread-safe o suficiente para ser lida de uma thread de captura dedicada.
"""

from __future__ import annotations

import abc
import sys
from pathlib import Path

import numpy as np

from ..mixagem import TAXA_PADRAO


class ErroFonteAudio(RuntimeError):
    """Falha ao abrir/ler uma fonte de áudio (mensagem já amigável em PT-BR)."""


class FonteAudio(abc.ABC):
    """Fonte de áudio que entrega PCM float32 mono a 16 kHz."""

    taxa: int = TAXA_PADRAO

    def __init__(self) -> None:
        self._avisos: list[str] = []
        #: níveis RMS por faixa (ex.: {"mic": 0.3, "loopback": 0.1}); a UI usa
        #: isto para desenhar as barras separadas de microfone e som do sistema.
        self.niveis: dict[str, float] = {}

    # -- ciclo de vida ----------------------------------------------------- #
    @abc.abstractmethod
    def abrir(self) -> None:
        """Prepara a fonte. Pode levantar ``ErroFonteAudio``."""

    @abc.abstractmethod
    def ler_bloco(self) -> np.ndarray | None:
        """Devolve o próximo bloco mono 16 kHz ou ``None`` no fim."""

    def parar(self) -> None:  # pragma: no cover - padrão sem recurso
        """Libera recursos. Implementações sobrescrevem se necessário."""

    # -- metadados --------------------------------------------------------- #
    @property
    def descricao(self) -> str:
        return self.__class__.__name__

    @property
    def avisos(self) -> list[str]:
        """Avisos não fatais (ex.: loopback indisponível), já em PT-BR."""
        return list(self._avisos)

    def _adicionar_aviso(self, msg: str) -> None:
        if msg not in self._avisos:
            self._avisos.append(msg)


def criar_fonte(caminho_arquivo: str | Path | None = None, acelerado: bool = False) -> FonteAudio:
    """Escolhe a fonte adequada à plataforma.

    * Se ``caminho_arquivo`` for informado, usa a fonte de arquivo (teste/Linux).
    * No Windows, usa a fonte de captura real (mic + loopback WASAPI).
    * No Linux sem arquivo, tenta ``sounddevice`` (captura simples de mic).
    """
    if caminho_arquivo:
        from .arquivo import FonteArquivo

        return FonteArquivo(caminho_arquivo, acelerado=acelerado)
    if sys.platform == "win32":
        from .windows import FonteWindows

        return FonteWindows()
    from .linux import FonteSounddevice

    return FonteSounddevice()
