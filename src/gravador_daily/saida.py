"""Formatação e gravação das saídas (.txt e .srt).

Formato dos arquivos: ``AAAA-MM-DD_HHMM_<nome>.txt`` e ``.srt``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .transcritor import Segmento


# --------------------------------------------------------------------------- #
# Tempo
# --------------------------------------------------------------------------- #
def _partes(segundos: float) -> tuple[int, int, int]:
    total = int(round(max(0.0, segundos)))
    return total // 3600, (total % 3600) // 60, total % 60


def formatar_hms(segundos: float) -> str:
    """``01:02:03`` — usado no cabeçalho e nas linhas do TXT."""
    h, m, s = _partes(segundos)
    return f"{h:02d}:{m:02d}:{s:02d}"


def formatar_tempo_srt(segundos: float) -> str:
    """``HH:MM:SS,mmm`` — timestamp do formato SRT."""
    total = max(0.0, segundos)
    inteiro = int(total)
    h = inteiro // 3600
    m = (inteiro % 3600) // 60
    s = inteiro % 60
    ms = int(round((total - inteiro) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
        if s == 60:
            s = 0
            m += 1
            if m == 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------------------------------------------------------- #
# Nome do arquivo
# --------------------------------------------------------------------------- #
_INVALIDOS = re.compile(r'[<>:"/\\\\|?*\x00-\x1f]')


def limpar_nome(nome: str, padrao: str = "Daily") -> str:
    nome = (nome or "").strip() or padrao
    nome = _INVALIDOS.sub("-", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    return nome[:80] or padrao


def nome_base(inicio: datetime, nome: str) -> str:
    """``2026-11-11_0930_Daily``."""
    return f"{inicio:%Y-%m-%d_%H%M}_{limpar_nome(nome)}"


# --------------------------------------------------------------------------- #
# Conteúdo
# --------------------------------------------------------------------------- #
def formatar_txt(
    segmentos: list[Segmento],
    nome: str,
    inicio: datetime,
    duracao_s: float | None = None,
) -> str:
    linhas = [
        f"Transcrição da reunião: {nome.strip() or 'Daily'}",
        f"Data: {inicio:%d/%m/%Y %H:%M}",
    ]
    if duracao_s is not None:
        linhas.append(f"Duração: {formatar_hms(duracao_s)}")
    linhas.append("Transcrição automática (faster-whisper, modelo small, português).")
    linhas.append("Pode conter erros. Revise antes de compartilhar.")
    linhas.append("-" * 60)
    linhas.append("")
    if not segmentos:
        linhas.append("(nenhuma fala reconhecida)")
    for seg in segmentos:
        texto = seg.texto.strip()
        if not texto:
            continue
        linhas.append(f"[{formatar_hms(seg.inicio)}] {texto}")
    return "\n".join(linhas).rstrip() + "\n"


def formatar_srt(segmentos: list[Segmento]) -> str:
    blocos = []
    for i, seg in enumerate(seg for seg in segmentos if seg.texto.strip()):
        blocos.append(
            f"{i + 1}\n"
            f"{formatar_tempo_srt(seg.inicio)} --> {formatar_tempo_srt(seg.fim)}\n"
            f"{seg.texto.strip()}\n"
        )
    return "\n".join(blocos)


def salvar_saidas(
    pasta: Path,
    base: str,
    segmentos: list[Segmento],
    nome: str,
    inicio: datetime,
    duracao_s: float | None = None,
) -> tuple[Path, Path]:
    """Grava ``<base>.txt`` e ``<base>.srt`` e devolve os caminhos."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_txt = pasta / f"{base}.txt"
    caminho_srt = pasta / f"{base}.srt"
    caminho_txt.write_text(
        formatar_txt(segmentos, nome, inicio, duracao_s), encoding="utf-8"
    )
    caminho_srt.write_text(formatar_srt(segmentos), encoding="utf-8")
    return caminho_txt, caminho_srt
