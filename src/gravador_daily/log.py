"""Log simples em arquivo, sem telemetria.

Windows: ``%LOCALAPPDATA%\\GravadorDaily\\log.txt``
Linux:   ``~/.local/share/GravadorDaily/log.txt``
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import pasta_local_usuario

_LOGGER = logging.getLogger("gravador_daily")
_configurado = False


def caminho_log() -> Path:
    return pasta_local_usuario() / "log.txt"


def configurar_log(nivel: int = logging.INFO) -> Path:
    """Configura o logger raiz do app gravando em arquivo. Idempotente."""
    global _configurado
    caminho = caminho_log()
    if not _configurado:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        manipulador = logging.FileHandler(caminho, encoding="utf-8")
        manipulador.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        raiz = logging.getLogger("gravador_daily")
        raiz.setLevel(nivel)
        raiz.addHandler(manipulador)
        raiz.propagate = False
        _configurado = True
    return caminho


def obter_logger(nome: str | None = None) -> logging.Logger:
    if nome:
        return logging.getLogger(f"gravador_daily.{nome}")
    return _LOGGER
