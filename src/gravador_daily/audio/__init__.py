"""Pacote de fontes de áudio.

A interface ``FonteAudio`` é a única coisa que o restante do app conhece. As
implementações concretas (Windows, arquivo, Linux/sounddevice) ficam aqui.
"""

from .base import FonteAudio, ErroFonteAudio, criar_fonte

__all__ = ["FonteAudio", "ErroFonteAudio", "criar_fonte"]
