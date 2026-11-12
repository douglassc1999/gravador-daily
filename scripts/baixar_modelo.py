#!/usr/bin/env python3
"""Baixa o modelo faster-whisper small para ``modelos/small`` (uso em dev/CI).

Uso:
    python scripts/baixar_modelo.py                 # -> modelos/small
    python scripts/baixar_modelo.py --destino outro

Baixa o repositório ``Systran/faster-whisper-small`` do Hugging Face. Requer
rede — é a única parte do projeto que usa internet, e só roda em desenvolvimento
ou no CI (nunca no executável entregue à usuária).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ID = "Systran/faster-whisper-small"
RAIZ = Path(__file__).resolve().parents[1]


def baixar(destino: Path) -> Path:
    destino = destino.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    try:
        from faster_whisper.utils import download_model
    except Exception:
        download_model = None

    if download_model is not None:
        print(f"Baixando {REPO_ID} via faster-whisper para {destino} …")
        caminho = download_model("small", output_dir=str(destino), local_files_only=False)
        print(f"Modelo em: {caminho}")
        return Path(caminho)

    # Alternativa: huggingface_hub direto.
    from huggingface_hub import snapshot_download  # type: ignore

    print(f"Baixando {REPO_ID} via huggingface_hub para {destino} …")
    caminho = snapshot_download(
        repo_id=REPO_ID, local_dir=str(destino), local_dir_use_symlinks=False
    )
    print(f"Modelo em: {caminho}")
    return Path(caminho)


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa o modelo Whisper small.")
    parser.add_argument(
        "--destino",
        type=Path,
        default=RAIZ / "modelos" / "small",
        help="pasta de destino (padrão: modelos/small)",
    )
    args = parser.parse_args(argv)
    try:
        caminho = baixar(args.destino)
    except Exception as exc:
        print(f"Erro ao baixar o modelo: {exc}", file=sys.stderr)
        return 1
    esperado = args.destino / "model.bin"
    if not esperado.exists():
        print(f"Aviso: {esperado} não foi criado.", file=sys.stderr)
        return 1
    print("Pronto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
