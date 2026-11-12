"""``--selftest``: valida que o executável carrega o modelo e transcreve.

Usado no smoke test do GitHub Actions (no Windows) e como checagem rápida local.
Não abre janela. Saída 0 = ok, != 0 = falha.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np

from .config import Config, carregar_config
from .log import configurar_log, obter_logger
from .mixagem import TAXA_PADRAO, salvar_wav
from .transcritor import ErroModeloAusente, WhisperMotor


def gerar_wav_sintetico(caminho: Path, segundos: float = 3.0, taxa: int = TAXA_PADRAO) -> Path:
    """Cria um WAV curto (tom com envelope) — não precisa de fala."""
    t = np.arange(int(segundos * taxa)) / taxa
    onda = 0.3 * np.sin(2 * np.pi * 220.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t))
    return salvar_wav(caminho, onda.astype(np.float32), taxa)


def executar_selftest(cfg: Config | None = None, wav: Path | None = None) -> int:
    configurar_log()
    log = obter_logger("selftest")
    cfg = cfg or carregar_config()

    print(f"[selftest] modelo: {cfg.modelo_path()}")

    if wav is None:
        tmp = Path(tempfile.mkdtemp(prefix="gravador-selftest-"))
        wav = gerar_wav_sintetico(tmp / "teste.wav", 3.0)
        print(f"[selftest] WAV sintético: {wav}")
    else:
        print(f"[selftest] WAV informado: {wav}")

    motor = WhisperMotor(cfg.modelo_path())
    try:
        motor.carregar()
    except ErroModeloAusente as exc:
        print(f"[selftest] ERRO: {exc}")
        return 2
    except Exception as exc:  # pragma: no cover - ambiente quebrado
        print(f"[selftest] ERRO ao carregar o modelo: {exc}")
        return 3

    from .mixagem import ler_wav_16k

    audio = ler_wav_16k(wav)
    try:
        segmentos = motor.transcrever(audio, 0.0)
    except Exception as exc:  # pragma: no cover
        print(f"[selftest] ERRO ao transcrever: {exc}")
        return 4

    print(f"[selftest] OK — modelo carregado, {len(segmentos)} segmento(s) retornado(s).")
    for seg in segmentos[:3]:
        print(f"    [{seg.inicio:.1f}-{seg.fim:.1f}] {seg.texto}")
    log.info("selftest OK com %d segmentos", len(segmentos))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="GravadorDaily",
        description="Grava reuniões e transcreve em português (faster-whisper).",
    )
    parser.add_argument("--selftest", action="store_true", help="testa o modelo e sai")
    parser.add_argument("--wav", type=Path, help="WAV usado no --selftest")
    parser.add_argument(
        "--fonte-arquivo",
        type=Path,
        help="usa um arquivo de áudio como fonte (teste no Linux)",
    )
    parser.add_argument(
        "--acelerado",
        action="store_true",
        help="com --fonte-arquivo, processa o mais rápido possível",
    )
    parser.add_argument(
        "--autoiniciar",
        action="store_true",
        help="começa a gravar assim que a janela abre",
    )
    parser.add_argument("--nome", type=str, help="nome da reunião")
    parser.add_argument("--pasta-saida", type=Path, help="pasta de saída")
    parser.add_argument("--modelo", type=Path, help="pasta do modelo Whisper")
    parser.add_argument(
        "--transcrever-arquivo",
        type=Path,
        help="transcreve um arquivo (mp3/wav/m4a/mp4) sem abrir a janela",
    )
    parser.add_argument("--versao", action="store_true", help="mostra a versão")
    args = parser.parse_args(argv)

    from . import __version__

    if args.versao:
        print(f"Gravador de Daily {__version__}")
        return 0

    cfg = carregar_config()
    if args.nome:
        cfg.nome_padrao = args.nome
    if args.pasta_saida:
        cfg.pasta_saida = str(args.pasta_saida)
    if args.modelo:
        cfg.modelo_dir = str(args.modelo)

    if args.selftest:
        return executar_selftest(cfg, args.wav)

    if args.transcrever_arquivo:
        return _transcrever_sem_ui(args.transcrever_arquivo, cfg)

    # Interface normal.
    from .app import iniciar_interface
    from .audio.base import criar_fonte

    if args.fonte_arquivo:
        caminho = args.fonte_arquivo
        acelerado = args.acelerado
        fabrica = lambda: criar_fonte(caminho, acelerado=acelerado)  # noqa: E731
    else:
        fabrica = None  # type: ignore[assignment]

    iniciar_interface(
        cfg=cfg, fabrica_fonte=fabrica, autoiniciar=args.autoiniciar
    )
    return 0


def _transcrever_sem_ui(caminho: Path, cfg: Config) -> int:
    from .log import configurar_log, obter_logger
    from .sessao import reprocessar

    configurar_log()
    log = obter_logger("cli")
    motor = WhisperMotor(cfg.modelo_path(), idioma=cfg.idioma)

    def progresso(fracao: float) -> None:
        print(f"\rTranscrevendo… {fracao * 100:5.1f}%", end="", flush=True)

    try:
        resultado = reprocessar(caminho, motor, cfg, ao_progresso=progresso)
    except ErroModeloAusente as exc:
        print(f"\nErro: {exc}")
        return 2
    except Exception as exc:
        log.exception("falha na transcrição via CLI")
        print(f"\nErro: {exc}")
        return 1
    print()
    print(f"Transcrição: {resultado.caminho_txt}")
    print(f"Legenda:     {resultado.caminho_srt}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
