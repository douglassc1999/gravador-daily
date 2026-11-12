"""Teste ponta a ponta da sessão de gravação (fonte de arquivo + motor falso)."""

from __future__ import annotations

import numpy as np

from gravador_daily import mixagem
from gravador_daily.audio.arquivo import FonteArquivo
from gravador_daily.config import Config
from gravador_daily.mixagem import TAXA_PADRAO, ler_wav
from gravador_daily.sessao import SessaoGravacao, gravacoes_pendentes, reprocessar
from gravador_daily.transcritor import MotorTranscricao, Segmento


class MotorFalso(MotorTranscricao):
    def transcrever(self, audio: np.ndarray, offset: float) -> list[Segmento]:
        duracao = audio.size / TAXA_PADRAO
        return [Segmento(offset, offset + duracao, f"fala {offset:.1f}s")]


def _gravar(tmp_path, segundos: float, manter_audio: bool = True):
    entrada = (0.2 * np.sin(np.linspace(0, 400, int(segundos * TAXA_PADRAO)))).astype(
        np.float32
    )
    caminho_entrada = mixagem.salvar_wav(tmp_path / "entrada.wav", entrada)

    cfg = Config(pasta_saida=str(tmp_path / "saida"), manter_audio=manter_audio)
    fonte = FonteArquivo(caminho_entrada, acelerado=True, bloco_s=0.5)
    sessao = SessaoGravacao(fonte, MotorFalso(), cfg, "Daily", tmp_path / "saida")
    sessao.iniciar()
    sessao.aguardar_captura(30)
    resultado = sessao.parar()
    return resultado, caminho_entrada


def test_sessao_gera_txt_srt_e_wav(tmp_path):
    resultado, _ = _gravar(tmp_path, 4.0)
    assert resultado.caminho_txt.exists()
    assert resultado.caminho_srt.exists()
    assert resultado.caminho_wav is not None and resultado.caminho_wav.exists()
    texto = resultado.caminho_txt.read_text(encoding="utf-8")
    assert "Transcrição da reunião: Daily" in texto
    assert "fala" in texto
    assert resultado.duracao_s >= 3.5


def test_sessao_wav_tem_16k_mono(tmp_path):
    resultado, _ = _gravar(tmp_path, 3.0)
    audio, taxa = ler_wav(resultado.caminho_wav)
    assert taxa == TAXA_PADRAO
    assert abs(audio.size / TAXA_PADRAO - 3.0) < 0.2


def test_sessao_respeita_manter_audio_false(tmp_path):
    resultado, _ = _gravar(tmp_path, 2.0, manter_audio=False)
    assert resultado.caminho_wav is None
    assert list((tmp_path / "saida").glob("*.wav")) == []


def test_gravacoes_pendentes_detecta_wav_sem_txt(tmp_path):
    pasta = tmp_path / "saida"
    pasta.mkdir()
    mixagem.salvar_wav(pasta / "2026-11-11_0930_Daily.wav", np.zeros(TAXA_PADRAO, dtype=np.float32))
    pendentes = gravacoes_pendentes(pasta)
    assert len(pendentes) == 1
    (pasta / "2026-11-11_0930_Daily.txt").write_text("ok", encoding="utf-8")
    assert gravacoes_pendentes(pasta) == []


def test_reprocessar_transcreve_wav_existente(tmp_path):
    pasta = tmp_path / "saida"
    pasta.mkdir()
    wav = pasta / "2026-11-11_0930_Daily.wav"
    mixagem.salvar_wav(wav, np.zeros(int(2 * TAXA_PADRAO), dtype=np.float32))

    progressos: list[float] = []
    resultado = reprocessar(wav, MotorFalso(), Config(), ao_progresso=progressos.append)
    assert resultado.caminho_txt.exists()
    assert resultado.caminho_srt.exists()
    assert progressos and progressos[-1] == 1.0
