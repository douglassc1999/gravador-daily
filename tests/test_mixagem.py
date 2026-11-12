"""Testes de mixagem, resampling, normalização e WAV."""

from __future__ import annotations

import numpy as np
import pytest

from gravador_daily.mixagem import (
    TAXA_PADRAO,
    concatenar,
    float_para_int16,
    int16_para_float,
    ler_wav,
    ler_wav_16k,
    misturar,
    para_mono,
    normalizar_pico,
    resample,
    rms,
    salvar_wav,
)


def test_para_mono_mede_canais():
    estereo = np.array([[1.0, 3.0], [2.0, 4.0]], dtype=np.float32)
    assert np.allclose(para_mono(estereo), [2.0, 3.0])


def test_resample_muda_tamanho_na_proporcao():
    origem = np.sin(np.linspace(0, 10, 44100)).astype(np.float32)  # 1 s @ 44,1 kHz
    destino = resample(origem, 44100, 16000)
    assert destino.dtype == np.float32
    assert abs(destino.size - 16000) <= 2


def test_resample_mesma_taxa_e_identidade():
    origem = np.arange(100, dtype=np.float32)
    assert np.array_equal(resample(origem, 16000, 16000), origem)


def test_resample_upsample_aproxima_valores():
    origem = np.array([0.0, 1.0, 0.0, -1.0], dtype=np.float32)
    destino = resample(origem, 4, 8)
    assert destino.size == 8
    assert destino[0] == pytest.approx(0.0)
    assert destino[-1] == pytest.approx(-1.0)


def test_normalizar_pico_limita_amplitude():
    alto = np.array([2.5, -3.0, 1.0], dtype=np.float32)
    saida = normalizar_pico(alto, pico=0.99)
    assert np.max(np.abs(saida)) <= 0.99 + 1e-6


def test_misturar_nao_estoura_com_duas_faixas_cheias():
    a = np.ones(1000, dtype=np.float32) * 0.9
    b = np.ones(1000, dtype=np.float32) * 0.9
    saida = misturar([a, b])
    assert np.max(np.abs(saida)) <= 1.0
    assert saida.size == 1000


def test_misturar_trunca_ao_menor():
    saida = misturar([np.ones(100, dtype=np.float32), np.ones(60, dtype=np.float32)])
    assert saida.size == 60


def test_misturar_preserva_uma_faixa():
    a = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    assert np.allclose(misturar([a]), a)


def test_rms_de_silencio_e_zero():
    assert rms(np.zeros(1000, dtype=np.float32)) == 0.0


def test_rms_de_onda_cheia():
    onda = np.sin(np.linspace(0, 2 * np.pi * 20, 16000)).astype(np.float32)
    assert 0.6 < rms(onda) < 0.8


def test_conversao_int16_roundtrip():
    original = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    volta = int16_para_float(float_para_int16(original))
    assert np.allclose(volta, original, atol=1e-3)


def test_wav_roundtrip(tmp_path):
    audio = np.sin(np.linspace(0, 50, 16000)).astype(np.float32) * 0.5
    caminho = salvar_wav(tmp_path / "a.wav", audio)
    lido, taxa = ler_wav(caminho)
    assert taxa == TAXA_PADRAO
    assert lido.size == audio.size
    assert np.allclose(lido, audio, atol=1e-3)


def test_ler_wav_16k_resample(tmp_path):
    import wave

    taxa = 8000
    dados = (np.zeros(taxa, dtype="<i2")).tobytes()
    caminho = tmp_path / "8k.wav"
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(dados)
    lido = ler_wav_16k(caminho)
    assert abs(lido.size - 16000) <= 2


def test_concatenar_blocos():
    saida = concatenar([np.ones(3, dtype=np.float32), np.zeros(2, dtype=np.float32)])
    assert saida.size == 5
