#!/usr/bin/env python3
"""Gera um WAV de teste em português para exercitar a transcrição.

* Se ``edge-tts`` estiver disponível (ou o pacote ``edge-tts`` no PATH), gera
  fala sintética em PT-BR a partir de um texto.
* Caso contrário, gera um tom com envelope — serve para testar o pipeline, mas o
  Whisper provavelmente não reconhecerá palavras.

Uso:
    python scripts/gerar_wav_teste.py --saida /tmp/fala.wav --segundos 180
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

TEXTO_PADRAO = (
    "Bom dia a todos. Esta é a nossa reunião diária de equipe. "
    "Vou começar atualizando o status das tarefas em andamento. "
    "Ontem finalizei a revisão do código e enviei o merge request. "
    "Hoje vou trabalhar na correção dos defeitos apontados. "
    "Não tenho bloqueios no momento. Agora passo a palavra para o próximo. "
)


def _gerar_fala(texto: str, saida: Path, voz: str) -> bool:
    """Tenta gerar fala com edge-tts. Devolve True se conseguiu."""
    exe = shutil.which("edge-tts")
    if exe is None:
        for cand in (
            Path.home() / ".hermes/installs",
        ):
            achados = list(cand.glob("*/environments/*/venv/bin/edge-tts")) if cand.exists() else []
            if achados:
                exe = str(achados[0])
                break
    if exe is None:
        return False
    try:
        subprocess.run(
            [exe, "--voice", voz, "--text", texto, "--write-media", str(saida)],
            check=True,
            capture_output=True,
        )
        return saida.exists() and saida.stat().st_size > 0
    except Exception as exc:
        print(f"Aviso: edge-tts falhou ({exc}); gerando tom.", file=sys.stderr)
        return False


def _gerar_tom(saida: Path, segundos: float, taxa: int = 16000) -> None:
    import wave

    t = np.arange(int(segundos * taxa)) / taxa
    onda = 0.3 * np.sin(2 * np.pi * 200.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * t))
    dados = (np.clip(onda, -1, 1) * 32767).astype("<i2")
    with wave.open(str(saida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(dados.tobytes())


def _converter_para_wav_16k(origem: Path, destino: Path) -> None:
    """Converte (mp3 do edge-tts) para WAV 16 kHz mono usando ffmpeg."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from gravador_daily.audio.arquivo import caminho_ffmpeg

    subprocess.run(
        [
            caminho_ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(origem),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(destino),
        ],
        check=True,
    )


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera WAV de teste em PT-BR.")
    parser.add_argument("--saida", type=Path, default=Path("fala_teste.wav"))
    parser.add_argument("--texto", type=str, default=TEXTO_PADRAO)
    parser.add_argument("--voz", type=str, default="pt-BR-AntonioNeural")
    parser.add_argument(
        "--repeticoes", type=int, default=1, help="repete o texto para ficar mais longo"
    )
    parser.add_argument("--segundos", type=float, default=0.0, help="usado só no modo tom")
    args = parser.parse_args(argv)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    texto = " ".join([args.texto] * max(1, args.repeticoes))

    with tempfile.TemporaryDirectory() as tmp:
        bruto = Path(tmp) / "fala.mp3"
        if _gerar_fala(texto, bruto, args.voz):
            _converter_para_wav_16k(bruto, args.saida)
            print(f"Fala PT-BR gerada: {args.saida}")
            return 0

    _gerar_tom(args.saida, args.segundos or 10.0)
    print(f"Tom gerado (sem TTS disponível): {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
