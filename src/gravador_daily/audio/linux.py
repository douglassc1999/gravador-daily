"""Fonte de áudio no Linux via ``sounddevice`` (apenas desenvolvimento/teste).

No Windows a captura real fica em ``windows.py``. Aqui capturamos só o
microfone padrão — suficiente para exercitar o pipeline no Linux. Se o
``sounddevice`` não estiver disponível ou não houver dispositivo, levanta
``ErroFonteAudio`` com mensagem clara.
"""

from __future__ import annotations

import queue

import numpy as np

from ..mixagem import TAXA_PADRAO, para_mono, resample
from .base import ErroFonteAudio, FonteAudio

BLOCO_S = 0.5


class FonteSounddevice(FonteAudio):
    def __init__(self, taxa: int = TAXA_PADRAO) -> None:
        super().__init__()
        self.taxa = taxa
        self._fila: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._taxa_disp = taxa

    def abrir(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - dependência opcional
            raise ErroFonteAudio(
                "sounddevice não está instalado; não é possível capturar áudio no Linux."
            ) from exc

        try:
            info = sd.query_devices(kind="input")
        except Exception as exc:
            raise ErroFonteAudio("Nenhum microfone disponível no sistema.") from exc

        self._taxa_disp = int(info["default_samplerate"])
        canais = max(1, min(2, int(info["max_input_channels"])))

        def _callback(indata, frames, time_info, status):  # noqa: ANN001
            self._fila.put(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self._taxa_disp,
                channels=canais,
                dtype="float32",
                blocksize=int(self._taxa_disp * BLOCO_S),
                callback=_callback,
            )
            self._stream.start()
        except Exception as exc:
            raise ErroFonteAudio(f"Não foi possível abrir o microfone: {exc}") from exc

    def ler_bloco(self) -> np.ndarray | None:
        if self._stream is None:
            self.abrir()
        try:
            dados = self._fila.get(timeout=2.0)
        except queue.Empty:
            return np.zeros(int(self.taxa * BLOCO_S), dtype=np.float32)
        mono = para_mono(dados)
        bloco = resample(mono, self._taxa_disp, self.taxa)
        self.niveis["microfone"] = float(np.sqrt(np.mean(np.square(bloco))))
        return bloco

    def parar(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    @property
    def descricao(self) -> str:
        return "Microfone (sounddevice/Linux)"
