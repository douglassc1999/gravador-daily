"""Mixagem, resampling, normalização e leitura/escrita de WAV.

Tudo em ``numpy`` puro, sem dependências de DSP externas. Áudio interno do app é
sempre ``float32`` mono a 16 kHz — o formato que o faster-whisper espera.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

TAXA_PADRAO = 16000


# --------------------------------------------------------------------------- #
# Conversões básicas
# --------------------------------------------------------------------------- #
def para_mono(bloco: np.ndarray) -> np.ndarray:
    """Converte um bloco (n, canais) para mono (n,) somando a média dos canais."""
    arr = np.asarray(bloco, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr.mean(axis=1).astype(np.float32)
    raise ValueError(f"Formato de áudio inesperado com {arr.ndim} dimensões")


def resample(bloco: np.ndarray, taxa_origem: int, taxa_destino: int = TAXA_PADRAO) -> np.ndarray:
    """Resampling linear simples (adequado para fala a 16 kHz).

    Não é de altíssima qualidade, mas é barato, determinístico e suficiente para
    fala capturada de microfone/loopback. Evita depender de bibliotecas C.
    """
    if taxa_origem == taxa_destino:
        return np.asarray(bloco, dtype=np.float32)
    arr = np.asarray(bloco, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return arr.astype(np.float32)
    n_dest = int(round(arr.size * taxa_destino / float(taxa_origem)))
    n_dest = max(n_dest, 1)
    # Interpola no eixo dos índices originais.
    eixo_orig = np.arange(arr.size, dtype=np.float64)
    eixo_dest = np.linspace(0.0, arr.size - 1, n_dest, dtype=np.float64)
    saida = np.interp(eixo_dest, eixo_orig, arr)
    return saida.astype(np.float32)


def normalizar_pico(bloco: np.ndarray, pico: float = 0.99) -> np.ndarray:
    """Escala o bloco para que o maior valor absoluto não ultrapasse ``pico``."""
    arr = np.asarray(bloco, dtype=np.float32)
    if arr.size == 0:
        return arr
    maximo = float(np.max(np.abs(arr)))
    if maximo <= 1e-9:
        return arr
    if maximo <= pico:
        return arr
    return (arr * (pico / maximo)).astype(np.float32)


def misturar(blocos: Sequence[np.ndarray], normalizar: bool = True) -> np.ndarray:
    """Soma faixas alinhadas e evita clipping.

    Faixas de tamanhos diferentes são truncadas ao menor comprimento. O ganho da
    soma é reduzido proporcionalmente ao número de faixas para não estourar.
    """
    validos = [np.asarray(b, dtype=np.float32).reshape(-1) for b in blocos if b is not None]
    validos = [b for b in validos if b.size > 0]
    if not validos:
        return np.zeros(0, dtype=np.float32)
    if len(validos) == 1:
        saida = validos[0].copy()
    else:
        menor = min(b.size for b in validos)
        saida = np.zeros(menor, dtype=np.float32)
        for b in validos:
            saida += b[:menor]
        # Compensa o ganho da soma para não passar de ~1.0.
        saida /= float(len(validos))
    if normalizar:
        saida = normalizar_pico(saida)
    return saida.astype(np.float32)


def rms(bloco: np.ndarray) -> float:
    """Nível RMS (0.0 a ~1.0) para alimentar a barra de nível da interface."""
    arr = np.asarray(bloco, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(arr))))


# --------------------------------------------------------------------------- #
# WAV (16 kHz mono, 16 bit PCM)
# --------------------------------------------------------------------------- #
def float_para_int16(bloco: np.ndarray) -> np.ndarray:
    arr = np.clip(np.asarray(bloco, dtype=np.float32), -1.0, 1.0)
    return (arr * 32767.0).astype(np.int16)


def int16_para_float(bloco: np.ndarray) -> np.ndarray:
    arr = np.asarray(bloco)
    return (arr.astype(np.float32) / 32768.0).astype(np.float32)


def salvar_wav(caminho: str | Path, audio: np.ndarray, taxa: int = TAXA_PADRAO) -> Path:
    """Escreve WAV PCM 16 bit mono."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = float_para_int16(audio)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(dados.tobytes())
    return caminho


def ler_wav(caminho: str | Path, taxa_destino: int = TAXA_PADRAO) -> tuple[np.ndarray, int]:
    """Lê um WAV PCM e devolve ``(float32 mono, taxa_original)``."""
    with wave.open(str(caminho), "rb") as w:
        n_canais = w.getnchannels()
        largura = w.getsampwidth()
        taxa = w.getframerate()
        quadros = w.readframes(w.getnframes())
    if largura == 2:
        arr = np.frombuffer(quadros, dtype=np.int16)
    elif largura == 1:
        arr = (np.frombuffer(quadros, dtype=np.uint8).astype(np.int16) - 128) << 8
    elif largura == 4:
        arr = np.frombuffer(quadros, dtype=np.int32)
        arr = (arr >> 16).astype(np.int16)
    else:
        raise ValueError(f"Largura de amostra não suportada: {largura} bytes")
    if n_canais > 1:
        arr = arr.reshape(-1, n_canais)
    mono = para_mono(int16_para_float(arr))
    return mono, taxa


def ler_wav_16k(caminho: str | Path, taxa_destino: int = TAXA_PADRAO) -> np.ndarray:
    mono, taxa = ler_wav(caminho, taxa_destino)
    return resample(mono, taxa, taxa_destino)


def concatenar(blocos: Iterable[np.ndarray]) -> np.ndarray:
    partes = [np.asarray(b, dtype=np.float32).reshape(-1) for b in blocos]
    partes = [p for p in partes if p.size > 0]
    if not partes:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(partes).astype(np.float32)
