"""Testes de configuração e caminhos."""

from __future__ import annotations

import json

import pytest

from gravador_daily import config as cfgmod


def test_config_padrao_tem_valores_sensatos():
    cfg = cfgmod.Config()
    assert cfg.nome_padrao == "Daily"
    assert cfg.manter_audio is True
    assert cfg.idioma == "pt"
    assert cfg.pasta_saida.endswith("Dailys")


def test_salvar_e_carregar_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))

    cfg = cfgmod.Config()
    cfg.pasta_saida = str(tmp_path / "saida")
    cfg.manter_audio = False
    cfg.nome_padrao = "Planning"
    caminho = cfgmod.salvar_config(cfg)
    assert caminho.exists()

    lido = cfgmod.carregar_config()
    assert lido.pasta_saida == str(tmp_path / "saida")
    assert lido.manter_audio is False
    assert lido.nome_padrao == "Planning"


def test_carregar_config_ignora_arquivo_corrompido(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    caminho = cfgmod.caminho_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("{ isto não é json", encoding="utf-8")

    cfg = cfgmod.carregar_config()
    assert cfg.nome_padrao == "Daily"


def test_carregar_config_cria_padroes_quando_ausente(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = cfgmod.carregar_config()
    assert cfg.manter_audio is True
    assert cfg.idioma == "pt"


def test_json_gerado_usa_chaves_esperadas(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    caminho = cfgmod.salvar_config(cfgmod.Config())
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert set(dados) == {"pasta_saida", "manter_audio", "nome_padrao", "modelo_dir", "idioma"}


def test_pasta_modelo_padrao_termina_em_small():
    assert cfgmod.pasta_modelo_padrao().parts[-2:] == ("modelos", "small")
