# -*- mode: python ; coding: utf-8 -*-
"""Especificação PyInstaller do Gravador de Daily (onedir, windowed).

Empacota:
* o código em ``src/gravador_daily`` (via ``lancador.py``);
* o modelo Whisper embutido em ``modelos/small``;
* as bibliotecas de transcrição (faster_whisper, ctranslate2, av, tokenizers,
  onnxruntime — este último usado pelo VAD Silero);
* um binário ffmpeg (via ``imageio-ffmpeg``), copiado para a raiz do pacote.

Gerar em Linux: ``pyinstaller gravador-daily.spec``. O alvo de produção é o
runner ``windows-latest`` do GitHub Actions.
"""

import importlib.util
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

raiz = Path(SPECPATH)
datas = []
binaries = []
hiddenimports = []

# Pacotes que trazem dados, binários e submódulos dinâmicos.
for pacote in (
    "faster_whisper",
    "ctranslate2",
    "av",
    "tokenizers",
    "onnxruntime",
    "huggingface_hub",
    "imageio_ffmpeg",
):
    try:
        d, b, h = collect_all(pacote)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as erro:  # pragma: no cover - pacote ausente
        print(f"[spec] aviso: não foi possível coletar {pacote}: {erro}")

# Modelo Whisper embutido (pasta modelos/small ao lado do executável).
modelo = raiz / "modelos"
if (modelo / "small").exists():
    datas.append((str(modelo), "modelos"))
else:
    print("[spec] AVISO: modelos/small não existe — rode scripts/baixar_modelo.py antes.")

# ffmpeg: garante um binário na raiz do pacote (nome específico no Windows).
ffmpeg_saida = raiz / "build" / "_ffmpeg"
ffmpeg_saida.mkdir(parents=True, exist_ok=True)
if importlib.util.find_spec("imageio_ffmpeg") is not None:
    import imageio_ffmpeg

    try:
        origem = Path(imageio_ffmpeg.get_ffmpeg_exe())
        nome_ffmpeg = "ffmpeg.exe" if origem.suffix.lower() == ".exe" else "ffmpeg"
        destino = ffmpeg_saida / nome_ffmpeg
        shutil.copy2(origem, destino)
        binaries.append((str(destino), "."))
        print(f"[spec] ffmpeg incluído: {nome_ffmpeg}")
    except Exception as erro:  # pragma: no cover
        print(f"[spec] aviso: ffmpeg não incluído ({erro})")
else:
    ffmpeg_do_sistema = shutil.which("ffmpeg")
    if ffmpeg_do_sistema:
        nome_ffmpeg = "ffmpeg.exe" if ffmpeg_do_sistema.endswith(".exe") else "ffmpeg"
        destino = ffmpeg_saida / nome_ffmpeg
        shutil.copy2(ffmpeg_do_sistema, destino)
        binaries.append((str(destino), "."))

hiddenimports += ["gravador_daily", "tkinter", "tkinter.ttk"]

a = Analysis(
    ["lancador.py"],
    pathex=[str(raiz / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GravadorDaily",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed: sem console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GravadorDaily",
)
