"""Testes de formatação TXT/SRT e nomes de arquivo."""

from __future__ import annotations

from datetime import datetime

from gravador_daily.saida import (
    formatar_hms,
    formatar_srt,
    formatar_tempo_srt,
    formatar_txt,
    limpar_nome,
    nome_base,
    salvar_saidas,
)
from gravador_daily.transcritor import Segmento


def test_formatar_hms():
    assert formatar_hms(0) == "00:00:00"
    assert formatar_hms(65) == "00:01:05"
    assert formatar_hms(3661) == "01:01:01"


def test_formatar_tempo_srt_com_milissegundos():
    assert formatar_tempo_srt(0) == "00:00:00,000"
    assert formatar_tempo_srt(1.5) == "00:00:01,500"
    assert formatar_tempo_srt(61.25) == "00:01:01,250"


def test_limpar_nome_remove_invalidos():
    limpo = limpar_nome('Planning <FISC>: "semanal"')
    for caractere in '<>:"/\\|?*':
        assert caractere not in limpo
    assert "Planning" in limpo and "FISC" in limpo and "semanal" in limpo
    assert limpar_nome("") == "Daily"
    assert limpar_nome("   ") == "Daily"


def test_nome_base_formato():
    base = nome_base(datetime(2026, 11, 11, 9, 30), "Daily")
    assert base == "2026-11-11_0930_Daily"


def test_formatar_txt_tem_cabecalho_e_linhas():
    segs = [
        Segmento(0.0, 2.0, "Bom dia a todos."),
        Segmento(65.0, 68.0, "Merge request enviado."),
    ]
    texto = formatar_txt(segs, "Daily", datetime(2026, 11, 11, 9, 30), 120.0)
    assert "Transcrição da reunião: Daily" in texto
    assert "11/11/2026 09:30" in texto
    assert "Duração: 00:02:00" in texto
    assert "[00:00:00] Bom dia a todos." in texto
    assert "[00:01:05] Merge request enviado." in texto


def test_formatar_txt_sem_fala():
    texto = formatar_txt([], "Daily", datetime(2026, 11, 11, 9, 30), 3.0)
    assert "(nenhuma fala reconhecida)" in texto


def test_formatar_srt_blocos_numerados():
    segs = [Segmento(0.0, 2.0, "Olá."), Segmento(3.0, 5.5, "Tudo bem?")]
    srt = formatar_srt(segs)
    linhas = srt.strip().split("\n")
    assert linhas[0] == "1"
    assert linhas[1] == "00:00:00,000 --> 00:00:02,000"
    assert linhas[2] == "Olá."
    assert "00:00:03,000 --> 00:00:05,500" in srt


def test_formatar_srt_ignora_vazios():
    segs = [Segmento(0.0, 1.0, "  "), Segmento(1.0, 2.0, "ok")]
    srt = formatar_srt(segs)
    assert srt.strip().startswith("1")
    assert "ok" in srt


def test_salvar_saidas_grava_dois_arquivos(tmp_path):
    segs = [Segmento(0.0, 1.0, "teste")]
    txt, srt = salvar_saidas(
        tmp_path, "2026-11-11_0930_Daily", segs, "Daily", datetime(2026, 11, 11, 9, 30), 60.0
    )
    assert txt.exists() and srt.exists()
    assert txt.name == "2026-11-11_0930_Daily.txt"
    assert "teste" in txt.read_text(encoding="utf-8")
