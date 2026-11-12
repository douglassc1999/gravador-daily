"""Interface gráfica (tkinter/ttk) do Gravador de Daily.

Uma janela única, em português do Brasil. Toda a lógica de áudio/transcrição
fica em ``sessao.py``/``transcritor.py``; aqui só desenhamos e reagimos.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import APP_TITULO
from .audio.base import FonteAudio, criar_fonte
from .config import Config, carregar_config, salvar_config
from .log import configurar_log, obter_logger
from .sessao import ResultadoGravacao, SessaoGravacao, gravacoes_pendentes, reprocessar
from .transcritor import MotorTranscricao, WhisperMotor

AVISO_LGPD = "Grave apenas reuniões em que todos foram avisados (LGPD)."


def _abrir_caminho(caminho: Path) -> None:
    """Abre um arquivo/pasta no programa padrão do sistema."""
    caminho = Path(caminho)
    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(caminho)])
        else:
            subprocess.Popen(["xdg-open", str(caminho)])
    except Exception as exc:  # pragma: no cover - depende do desktop
        raise RuntimeError(f"Não foi possível abrir '{caminho}': {exc}") from exc


def _formatar_cronometro(segundos: float) -> str:
    total = int(segundos)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


class Aplicativo:
    """Janela principal."""

    def __init__(
        self,
        cfg: Config | None = None,
        fabrica_fonte: Callable[[], FonteAudio] | None = None,
        motor: MotorTranscricao | None = None,
        autoiniciar: bool = False,
    ) -> None:
        self.log = obter_logger("app")
        self.cfg = cfg or carregar_config()
        self._fabrica_fonte = fabrica_fonte
        self._motor = motor
        self._autoiniciar = autoiniciar

        self.raiz = tk.Tk()
        self.raiz.title(APP_TITULO)
        self.raiz.geometry("600x660")
        self.raiz.minsize(520, 620)

        self._sessao: SessaoGravacao | None = None
        self._gravando = False
        self._niveis: dict[str, float] = {}
        self._status = "Pronto."
        self._progresso = 0.0
        self._resultado: ResultadoGravacao | None = None
        self._trabalhando = False

        self._montar()
        self._verificar_pendentes()
        if self._autoiniciar:
            self.raiz.after(500, self._ao_clicar_gravar)

    # ------------------------------------------------------------------ #
    # Montagem da interface
    # ------------------------------------------------------------------ #
    def _montar(self) -> None:
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except Exception:
            pass
        estilo.configure("Gravar.TButton", font=("Segoe UI", 16, "bold"), padding=14)
        estilo.configure("Cronometro.TLabel", font=("Segoe UI", 26, "bold"))
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 15, "bold"))
        estilo.configure("Aviso.TLabel", font=("Segoe UI", 8), foreground="#666666")

        raiz = ttk.Frame(self.raiz, padding=16)
        raiz.pack(fill="both", expand=True)

        ttk.Label(raiz, text=APP_TITULO, style="Titulo.TLabel").pack(anchor="w")

        # Nome da reunião
        linha_nome = ttk.Frame(raiz)
        linha_nome.pack(fill="x", pady=(10, 0))
        ttk.Label(linha_nome, text="Nome da reunião:").pack(side="left")
        self.var_nome = tk.StringVar(value=self.cfg.nome_padrao)
        ttk.Entry(linha_nome, textvariable=self.var_nome).pack(
            side="left", fill="x", expand=True, padx=(8, 0)
        )

        # Botão gravar
        self.btn_gravar = ttk.Button(
            raiz, text="● Gravar", style="Gravar.TButton", command=self._ao_clicar_gravar
        )
        self.btn_gravar.pack(fill="x", pady=(14, 4))

        # Cronômetro
        self.lbl_cronometro = ttk.Label(
            raiz, text="00:00:00", style="Cronometro.TLabel", anchor="center"
        )
        self.lbl_cronometro.pack(fill="x")

        # Níveis
        quadro_niveis = ttk.LabelFrame(raiz, text="Níveis de áudio", padding=8)
        quadro_niveis.pack(fill="x", pady=(10, 0))
        self.barra_mic = self._criar_barra(quadro_niveis, "Microfone")
        self.barra_sistema = self._criar_barra(quadro_niveis, "Som do computador")

        # Status / progresso
        quadro_status = ttk.LabelFrame(raiz, text="Status", padding=8)
        quadro_status.pack(fill="x", pady=(10, 0))
        self.lbl_status = ttk.Label(quadro_status, text=self._status, wraplength=480)
        self.lbl_status.pack(anchor="w")
        self.barra_progresso = ttk.Progressbar(
            quadro_status, mode="determinate", maximum=100
        )
        self.barra_progresso.pack(fill="x", pady=(6, 0))

        # Pendência de transcrição
        self.quadro_pendente = ttk.Frame(raiz)
        self.lbl_pendente = ttk.Label(
            self.quadro_pendente, text="Há uma gravação não transcrita."
        )
        self.lbl_pendente.pack(side="left")
        self.btn_pendente = ttk.Button(
            self.quadro_pendente, text="Transcrever", command=self._ao_transcrever_pendente
        )
        self.btn_pendente.pack(side="right")

        # Botões de saída
        quadro_botoes = ttk.Frame(raiz)
        quadro_botoes.pack(fill="x", pady=(12, 0))
        self.btn_abrir_pasta = ttk.Button(
            quadro_botoes, text="Abrir pasta", command=self._ao_abrir_pasta
        )
        self.btn_abrir_pasta.pack(side="left")
        self.btn_abrir_transcricao = ttk.Button(
            quadro_botoes,
            text="Abrir transcrição",
            command=self._ao_abrir_transcricao,
            state="disabled",
        )
        self.btn_abrir_transcricao.pack(side="left", padx=(8, 0))
        self.btn_alterar_pasta = ttk.Button(
            quadro_botoes, text="Alterar pasta", command=self._ao_alterar_pasta
        )
        self.btn_alterar_pasta.pack(side="right")

        # Ação secundária
        self.btn_transcrever_arquivo = ttk.Button(
            raiz, text="Transcrever arquivo de áudio…", command=self._ao_transcrever_arquivo
        )
        self.btn_transcrever_arquivo.pack(fill="x", pady=(10, 0))

        # Pasta de saída atual + aviso LGPD
        self.lbl_pasta = ttk.Label(
            raiz, text=f"Pasta de saída: {self.cfg.pasta_saida}", style="Aviso.TLabel"
        )
        self.lbl_pasta.pack(anchor="w", pady=(10, 0))
        ttk.Label(raiz, text=AVISO_LGPD, style="Aviso.TLabel").pack(anchor="w")

        self._loop_ui()

    def _criar_barra(self, pai: tk.Widget, rotulo: str) -> ttk.Progressbar:
        linha = ttk.Frame(pai)
        linha.pack(fill="x", pady=2)
        ttk.Label(linha, text=rotulo, width=18).pack(side="left")
        barra = ttk.Progressbar(linha, mode="determinate", maximum=100)
        barra.pack(side="left", fill="x", expand=True, padx=(8, 0))
        return barra

    # ------------------------------------------------------------------ #
    # Estado / atualização periódica
    # ------------------------------------------------------------------ #
    def _definir_status(self, texto: str) -> None:
        self._status = texto
        self.log.info("status: %s", texto)

    def _ao_nivel(self, niveis: dict[str, float]) -> None:
        self._niveis = dict(niveis)

    def _ao_progresso(self, fracao: float) -> None:
        self._progresso = max(0.0, min(1.0, fracao))

    def _loop_ui(self) -> None:
        self.lbl_status.configure(text=self._status)
        self.barra_progresso.configure(value=self._progresso * 100)

        if self._sessao is not None and self._gravando:
            self.lbl_cronometro.configure(
                text=_formatar_cronometro(self._sessao.duracao)
            )
        niveis = self._niveis
        if niveis:
            geral = max(niveis.values())
            mic = niveis.get("mic", niveis.get("microfone", geral))
            sistema = niveis.get("loopback", geral)
        else:
            mic = sistema = 0.0
        self.barra_mic.configure(value=min(100.0, mic * 100))
        self.barra_sistema.configure(value=min(100.0, sistema * 100))
        self.raiz.after(200, self._loop_ui)

    # ------------------------------------------------------------------ #
    # Gravação
    # ------------------------------------------------------------------ #
    def _obter_motor(self) -> MotorTranscricao:
        if self._motor is None:
            nucleos = os.cpu_count() or 4
            self._motor = WhisperMotor(
                self.cfg.modelo_path(),
                idioma=self.cfg.idioma,
                cpu_threads=max(2, nucleos - 2),
            )
        return self._motor

    def _ao_clicar_gravar(self) -> None:
        if self._trabalhando:
            return
        if not self._gravando:
            self._iniciar_gravacao()
        else:
            self._parar_gravacao()

    def _iniciar_gravacao(self) -> None:
        self._resultado = None
        self._progresso = 0.0
        nome = self.var_nome.get().strip() or self.cfg.nome_padrao
        fonte = (
            self._fabrica_fonte()
            if self._fabrica_fonte is not None
            else criar_fonte()
        )
        sessao = SessaoGravacao(
            fonte=fonte,
            motor=self._obter_motor(),
            cfg=self.cfg,
            nome=nome,
            pasta_saida=self.cfg.pasta_saida_path(),
            ao_status=self._definir_status,
            ao_nivel=self._ao_nivel,
            ao_progresso=self._ao_progresso,
        )
        self._trabalhando = True

        def tarefa() -> None:
            try:
                sessao.iniciar()
                self._sessao = sessao
                self._gravando = True
                self.raiz.after(0, self._pos_iniciar)
            except Exception as exc:
                self.log.exception("falha ao iniciar gravação")
                self.raiz.after(0, lambda: self._erro("Não foi possível iniciar a gravação", exc))
            finally:
                self._trabalhando = False

        threading.Thread(target=tarefa, daemon=True, name="iniciar-gravacao").start()

    def _pos_iniciar(self) -> None:
        self.btn_gravar.configure(text="■ Parar")
        self.btn_abrir_transcricao.configure(state="disabled")
        avisos = self._sessao.avisos if self._sessao else []
        if avisos:
            self._definir_status(" | ".join(avisos))

    def _parar_gravacao(self) -> None:
        sessao = self._sessao
        if sessao is None:
            return
        self._gravando = False
        self._trabalhando = True
        self.btn_gravar.configure(state="disabled")
        self._definir_status("Finalizando gravação e transcrevendo o restante…")

        def tarefa() -> None:
            try:
                resultado = sessao.parar()
                self.raiz.after(0, lambda: self._pos_parar(resultado))
            except Exception as exc:
                self.log.exception("falha ao parar/transcrever")
                self.raiz.after(0, lambda: self._erro("Erro ao finalizar a gravação", exc))
            finally:
                self._trabalhando = False

        threading.Thread(target=tarefa, daemon=True, name="parar-gravacao").start()

    def _pos_parar(self, resultado: ResultadoGravacao) -> None:
        self._sessao = None
        self._resultado = resultado
        self.btn_gravar.configure(text="● Gravar", state="normal")
        self.btn_abrir_transcricao.configure(state="normal")
        self._definir_status(
            f"Pronto. Transcrição salva em {resultado.caminho_txt.name}"
        )
        self._progresso = 1.0
        self._niveis = {}

    # ------------------------------------------------------------------ #
    # Ações de arquivos
    # ------------------------------------------------------------------ #
    def _ao_abrir_pasta(self) -> None:
        pasta = self.cfg.pasta_saida_path()
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            _abrir_caminho(pasta)
        except RuntimeError as exc:
            messagebox.showwarning(APP_TITULO, str(exc))

    def _ao_abrir_transcricao(self) -> None:
        if self._resultado is None:
            return
        try:
            _abrir_caminho(self._resultado.caminho_txt)
        except RuntimeError as exc:
            messagebox.showwarning(APP_TITULO, str(exc))

    def _ao_alterar_pasta(self) -> None:
        escolhida = filedialog.askdirectory(
            title="Escolha a pasta onde salvar as transcrições",
            initialdir=self.cfg.pasta_saida,
        )
        if escolhida:
            self.cfg.pasta_saida = escolhida
            salvar_config(self.cfg)
            self.lbl_pasta.configure(text=f"Pasta de saída: {escolhida}")

    # ------------------------------------------------------------------ #
    # Reprocessamento
    # ------------------------------------------------------------------ #
    def _verificar_pendentes(self) -> None:
        pendentes = gravacoes_pendentes(self.cfg.pasta_saida_path())
        if pendentes:
            self._pendente = pendentes[0]
            self.quadro_pendente.pack(fill="x", pady=(8, 0), after=self.barra_progresso.master)
            self._definir_status("Há uma gravação não transcrita.")
        else:
            self._pendente = None

    def _ao_transcrever_pendente(self) -> None:
        if self._pendente is None or self._trabalhando:
            return
        self._transcrever_arquivo(self._pendente)

    def _ao_transcrever_arquivo(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Escolha um arquivo de áudio ou vídeo",
            filetypes=[
                ("Áudio/Vídeo", "*.mp3 *.wav *.m4a *.mp4 *.ogg *.flac"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if caminho:
            self._transcrever_arquivo(Path(caminho))

    def _transcrever_arquivo(self, caminho: Path) -> None:
        self._trabalhando = True
        self.btn_transcrever_arquivo.configure(state="disabled")
        if self._pendente is not None:
            self.btn_pendente.configure(state="disabled")
        self._definir_status(f"Transcrevendo {caminho.name}…")

        def tarefa() -> None:
            try:
                resultado = reprocessar(
                    caminho, self._obter_motor(), self.cfg, ao_progresso=self._ao_progresso
                )
                self.raiz.after(0, lambda: self._pos_parar(resultado))
                self.raiz.after(0, lambda: self.quadro_pendente.pack_forget())
            except Exception as exc:
                self.log.exception("falha ao transcrever arquivo")
                self.raiz.after(0, lambda: self._erro("Erro ao transcrever o arquivo", exc))
            finally:
                self._trabalhando = False
                self.raiz.after(0, lambda: self.btn_transcrever_arquivo.configure(state="normal"))

        threading.Thread(target=tarefa, daemon=True, name="transcrever-arquivo").start()

    # ------------------------------------------------------------------ #
    def _erro(self, titulo: str, exc: Exception) -> None:
        self.btn_gravar.configure(text="● Gravar", state="normal")
        self._definir_status(f"{titulo}: {exc}")
        messagebox.showerror(APP_TITULO, f"{titulo}.\n\n{exc}")

    def executar(self) -> None:
        self.raiz.mainloop()

    def fechar(self) -> None:
        if self._sessao is not None and self._gravando:
            try:
                self._sessao.parar()
            except Exception:
                pass
        self.raiz.destroy()


def iniciar_interface(
    cfg: Config | None = None,
    fabrica_fonte: Callable[[], FonteAudio] | None = None,
    motor: MotorTranscricao | None = None,
    autoiniciar: bool = False,
) -> None:
    configurar_log()
    app = Aplicativo(cfg=cfg, fabrica_fonte=fabrica_fonte, motor=motor, autoiniciar=autoiniciar)
    app.executar()
