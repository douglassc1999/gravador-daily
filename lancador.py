#!/usr/bin/env python3
"""Ponto de entrada do executável empacotado (PyInstaller).

Mantido na raiz para que o ``gravador-daily.spec`` tenha um alvo simples.
"""

import sys
from pathlib import Path

# Em desenvolvimento, garante que ``src`` esteja no caminho.
_RAIZ = Path(__file__).resolve().parent
_SRC = _RAIZ / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gravador_daily.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
