"""Testes da transcrição incremental (fila + thread) com um motor falso."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from gravador_daily.mixagem import TAXA_PADRAO, salvar_wav
from gravador_daily.transcritor import (
    MotorTranscricao,
    Segmento,
    TranscricaoIncremental,
    transcrever_wav,
)


class MotorFalso(MotorTranscricao):
    """Devolve um segmento por trecho, com o texto indicando o offset."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[float, float]] = []
        self.threads: set[int] = set()
        self.primeiro_evento = threading.Event()

    def transcrever(self, audio: np.ndarray, offset: float) -> list[Segmento]:
        self.threads.add(threading.get_ident())
        self.primeiro_evento.set()
        duracao = audio.size / TAXA_PADRAO
        self.chamadas.append((offset, duracao))
        # Simula 0,05 s de trabalho para exercitar a thread.
        time.sleep(0.05)
        return [Segmento(offset, offset + duracao, f"trecho em {offset:.1f}s")]


def _audio(segundos: float) -> np.ndarray:
    n = int(segundos * TAXA_PADRAO)
    t = np.linspace(0, 1, n, endpoint=False)
    return (0.1 * np.sin(2 * np.pi * 5 * t)).astype(np.float32)


def test_incremental_transcreve_tudo_com_offsets_crescentes():
    motor = MotorFalso()
    inc = TranscricaoIncremental(motor, alvo_s=10.0, busca_s=2.0, min_s=3.0)
    inc.iniciar()
    bloco = _audio(1.0)
    for _ in range(35):  # 35 s -> vários trechos
        inc.alimentar(bloco)
    segmentos = inc.finalizar()

    assert segmentos, "deveria haver segmentos"
    inicios = [s.inicio for s in segmentos]
    assert inicios == sorted(inicios), "offsets devem ser crescentes"
    # Cobre praticamente todo o áudio enviado.
    assert segmentos[-1].fim >= 34.0
    coberto = sum(s.fim - s.inicio for s in segmentos)
    assert coberto >= 34.0


def test_incremental_roda_a_transcricao_fora_da_thread_principal():
    motor = MotorFalso()
    inc = TranscricaoIncremental(motor, alvo_s=2.0, busca_s=0.5, min_s=1.0)
    inc.iniciar()
    for _ in range(6):
        inc.alimentar(_audio(1.0))
    inc.finalizar()
    assert motor.threads, "o motor deveria ser chamado"
    assert threading.get_ident() not in motor.threads


def test_incremental_progresso_chega_a_100():
    motor = MotorFalso()
    progressos: list[float] = []
    inc = TranscricaoIncremental(
        motor, alvo_s=5.0, busca_s=1.0, min_s=1.0, ao_progresso=progressos.append
    )
    inc.iniciar()
    for _ in range(10):
        inc.alimentar(_audio(1.0))
    inc.finalizar()
    assert progressos and progressos[-1] == 1.0
    assert inc.progresso == 1.0


def test_incremental_nao_perde_audio_nas_bordas():
    motor = MotorFalso()
    inc = TranscricaoIncremental(motor, alvo_s=3.0, busca_s=0.5, min_s=1.0)
    inc.iniciar()
    rng = np.random.RandomState(1)
    for _ in range(12):
        inc.alimentar(rng.randn(TAXA_PADRAO // 2).astype(np.float32) * 0.1)
    segmentos = inc.finalizar()
    total = sum(s.fim - s.inicio for s in segmentos)
    assert total == pytest.approx(6.0, abs=0.2)


def test_transcrever_wav_reprocessa_arquivo(tmp_path):
    audio = _audio(8.0)
    caminho = salvar_wav(tmp_path / "gravacao.wav", audio)
    motor = MotorFalso()
    segmentos = transcrever_wav(caminho, motor, alvo_s=3.0)
    assert segmentos
    assert segmentos[-1].fim >= 7.0


def test_erro_do_motor_e_propagado():
    class MotorRuim(MotorTranscricao):
        def transcrever(self, audio, offset):
            raise RuntimeError("falha simulada")

    inc = TranscricaoIncremental(MotorRuim(), alvo_s=1.0, busca_s=0.2, min_s=0.5)
    inc.iniciar()
    for _ in range(4):
        inc.alimentar(_audio(1.0))
    with pytest.raises(RuntimeError, match="falha simulada"):
        inc.finalizar()
