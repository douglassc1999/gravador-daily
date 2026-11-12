"""Configuração persistida e resolução de caminhos do aplicativo.

No Windows usamos ``%APPDATA%`` para o ``config.json`` e ``%LOCALAPPDATA%`` para
o log. No Linux (desenvolvimento) usamos os equivalentes XDG. Nada aqui depende
de rede nem de telemetria.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NOME = "GravadorDaily"

# Nome padrão de reunião e pasta padrão de saída.
NOME_PADRAO = "Daily"


# --------------------------------------------------------------------------- #
# Caminhos do sistema
# --------------------------------------------------------------------------- #
def _raiz_projeto() -> Path:
    """Raiz do repositório em desenvolvimento (…/gravador-daily)."""
    return Path(__file__).resolve().parents[2]


def esta_empacotado() -> bool:
    """True quando rodando dentro do PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def pasta_app() -> Path:
    """Pasta base do aplicativo (onde vive ``modelos/`` e o ffmpeg embutido)."""
    if esta_empacotado():
        exe = Path(sys.executable).resolve().parent
        # PyInstaller 6 (onedir) coloca os dados em ``_internal`` (sys._MEIPASS).
        meipass = getattr(sys, "_MEIPASS", None)
        for base in ([Path(meipass)] if meipass else []) + [exe, exe / "_internal"]:
            if (base / "modelos").exists():
                return base
        return exe
    return _raiz_projeto()


def pasta_dados_usuario() -> Path:
    """Pasta persistente de dados (config, log, gravações pendentes)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NOME


def pasta_local_usuario() -> Path:
    """Pasta de dados locais (log)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NOME


def documentos() -> Path:
    """Melhor palpite para a pasta Documentos do usuário."""
    if sys.platform == "win32":
        perfil = Path(os.environ.get("USERPROFILE") or Path.home())
        return perfil / "Documents"
    # Linux: usa ~/Documentos se existir, senão ~/Documents, senão ~.
    for nome in ("Documentos", "Documents"):
        cand = Path.home() / nome
        if cand.exists():
            return cand
    return Path.home()


def pasta_saida_padrao() -> Path:
    return documentos() / "Dailys"


def pasta_modelo_padrao() -> Path:
    """Pasta do modelo Whisper embutido ao lado do executável."""
    return pasta_app() / "modelos" / "small"


def caminho_config() -> Path:
    return pasta_dados_usuario() / "config.json"


# --------------------------------------------------------------------------- #
# Estrutura de configuração
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    pasta_saida: str = field(default_factory=lambda: str(pasta_saida_padrao()))
    manter_audio: bool = True
    nome_padrao: str = NOME_PADRAO
    modelo_dir: str = field(default_factory=lambda: str(pasta_modelo_padrao()))
    idioma: str = "pt"

    def pasta_saida_path(self) -> Path:
        return Path(self.pasta_saida).expanduser()

    def modelo_path(self) -> Path:
        return Path(self.modelo_dir).expanduser()


def carregar_config() -> Config:
    """Lê o ``config.json``; se ausente/corrompido, devolve os padrões."""
    caminho = caminho_config()
    cfg = Config()
    try:
        if caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            for campo in ("pasta_saida", "manter_audio", "nome_padrao", "modelo_dir", "idioma"):
                if campo in dados and dados[campo] is not None:
                    setattr(cfg, campo, dados[campo])
    except Exception:  # pragma: no cover - config ilegível não deve derrubar o app
        pass
    return cfg


def salvar_config(cfg: Config) -> Path:
    """Grava o ``config.json`` criando a pasta se necessário."""
    caminho = caminho_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho
