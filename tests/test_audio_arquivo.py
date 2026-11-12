"""Testes da fonte de áudio a partir de arquivo (ffmpeg)."""

from __future__ import annotations

import numpy as np
import pytest

from gravador_daily import mixagem
from gravador_daily.audio.arquivo import FonteArquivo
from gravador_daily.mixagem import TAXA_PADRAO


def _wav_teste(tmp_path, segundos: float = 2.0):
    audio = (0.2 * np.sin(np.linspace(0, 200, int(segundos * TAXA_PADRAO)))).astype(
        np.float32
    )
    return mixagem.salvar_wav(tmp_path / "entrada.wav", audio)


def test_fonte_arquivo_entrega_blocos_16k(tmp_path):
    caminho = _wav_teste(tmp_path, 2.0)
    fonte = FonteArquivo(caminho, acelerado=True, bloco_s=0.5)
    fonte.abrir()
    blocos = []
    while True:
        bloco = fonte.ler_bloco()
        if bloco is None:
            break
        blocos.append(bloco)
    fonte.parar()
    total = sum(b.size for b in blocos)
    assert abs(total / TAXA_PADRAO - 2.0) < 0.1
    assert all(b.dtype == np.float32 for b in blocos)


def test_fonte_arquivo_acelerado_rapido(tmp_path):
    import time

    caminho = _wav_teste(tmp_path, 3.0)
    fonte = FonteArquivo(caminho, acelerado=True)
    fonte.abrir()
    inicio = time.monotonic()
    while fonte.ler_bloco() is not None:
        pass
    duracao = time.monotonic() - inicio
    fonte.parar()
    assert duracao < 1.0, "modo acelerado não deve dormir"


def test_fonte_arquivo_inexistente_levanta_erro(tmp_path):
    from gravador_daily.audio.base import ErroFonteAudio

    fonte = FonteArquivo(tmp_path / "nao_existe.wav")
    with pytest.raises(ErroFonteAudio):
        fonte.abrir()


def test_fonte_arquivo_define_nivel(tmp_path):
    caminho = _wav_teste(tmp_path, 1.0)
    fonte = FonteArquivo(caminho, acelerado=True)
    fonte.abrir()
    fonte.ler_bloco()
    fonte.parar()
    assert "arquivo" in fonte.niveis
