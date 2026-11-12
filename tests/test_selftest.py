"""Teste do ``--selftest`` e do gerador de WAV (exige o modelo baixado)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gravador_daily.__main__ import executar_selftest, gerar_wav_sintetico
from gravador_daily.config import Config, pasta_modelo_padrao


def _modelo_disponivel() -> bool:
    return (pasta_modelo_padrao() / "model.bin").exists()


@pytest.mark.modelo
@pytest.mark.skipif(not _modelo_disponivel(), reason="modelo small não baixado")
def test_selftest_retorna_zero(tmp_path, capsys):
    cfg = Config(modelo_dir=str(pasta_modelo_padrao()))
    codigo = executar_selftest(cfg)
    assert codigo == 0
    assert "OK" in capsys.readouterr().out


def test_gerar_wav_sintetico(tmp_path):
    caminho = gerar_wav_sintetico(tmp_path / "t.wav", 1.0)
    assert caminho.exists()
    assert caminho.stat().st_size > 1000


@pytest.mark.modelo
@pytest.mark.skipif(not _modelo_disponivel(), reason="modelo small não baixado")
def test_selftest_sem_modelo_indica_erro(tmp_path):
    cfg = Config(modelo_dir=str(tmp_path / "inexistente"))
    assert executar_selftest(cfg) == 2
