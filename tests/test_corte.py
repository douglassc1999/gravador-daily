"""Testes do corte em silêncio e do planejamento de trechos."""

from __future__ import annotations

import numpy as np

from gravador_daily.mixagem import TAXA_PADRAO
from gravador_daily.transcritor import encontrar_corte, planejar_cortes


def _fala_com_silencio(inicio_s: float, duracao_s: float) -> np.ndarray:
    """Sinal com fala (ruído) e um trecho de silêncio em [inicio, inicio+duracao]."""
    total = 60 * TAXA_PADRAO
    audio = (np.random.RandomState(0).randn(total) * 0.2).astype(np.float32)
    a = int(inicio_s * TAXA_PADRAO)
    b = a + int(duracao_s * TAXA_PADRAO)
    audio[a:b] = 0.0
    return audio


def test_encontrar_corte_corta_no_silencio():
    audio = _fala_com_silencio(30.0, 2.0)
    alvo = int(31.0 * TAXA_PADRAO)  # dentro do silêncio
    corte = encontrar_corte(audio, alvo, busca=int(5 * TAXA_PADRAO))
    # O corte deve cair dentro do trecho silencioso.
    assert 30.0 * TAXA_PADRAO <= corte <= 32.0 * TAXA_PADRAO


def test_encontrar_corte_respeita_minimo():
    audio = _fala_com_silencio(30.0, 2.0)
    alvo = int(10.0 * TAXA_PADRAO)
    minimo = int(25.0 * TAXA_PADRAO)
    corte = encontrar_corte(audio, alvo, busca=int(1 * TAXA_PADRAO), minimo=minimo)
    assert corte >= minimo


def test_planejar_cortes_cobre_todo_o_audio():
    audio = _fala_com_silencio(30.0, 0.2)
    trechos = planejar_cortes(audio, alvo_s=20.0, busca_s=2.0)
    assert trechos[0][0] == 0
    assert trechos[-1][1] == audio.size
    # Sem buracos nem sobreposições.
    for (_, fim), (prox, _) in zip(trechos, trechos[1:]):
        assert fim == prox


def test_planejar_cortes_trecho_curto():
    audio = np.zeros(int(5 * TAXA_PADRAO), dtype=np.float32)
    trechos = planejar_cortes(audio, alvo_s=45.0)
    assert len(trechos) == 1
    assert trechos[0] == (0, audio.size)


def test_corte_nao_avanca_menos_que_o_minimo():
    audio = (np.ones(120 * TAXA_PADRAO, dtype=np.float32) * 0.3)
    trechos = planejar_cortes(audio, alvo_s=45.0, min_s=5.0)
    for inicio, fim in trechos[:-1]:
        assert (fim - inicio) / TAXA_PADRAO >= 5.0
