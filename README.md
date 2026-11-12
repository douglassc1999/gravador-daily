# Gravador de Daily

Aplicativo de desktop para Windows que grava **microfone + som do computador**,
transcreve em **português** (faster-whisper, na CPU) e salva um `.txt` (e `.srt`)
por reunião. Sem telemetria e sem rede em tempo de execução — só o script de
download do modelo usa internet, e apenas em desenvolvimento/CI.

> **Autora do projeto:** Douglas Carvalho — uso pessoal (dailys de equipe).

---

## O que ele faz

1. Uma janela única (tkinter/ttk), em português: botão **Gravar** (vira
   **Parar**), cronômetro, nível do microfone e do som do computador, status com
   progresso da transcrição, botões **Abrir pasta** / **Abrir transcrição**.
2. Captura (Windows): microfone padrão **+** loopback WASAPI do dispositivo de
   saída padrão, mixados em mono 16 kHz `float32`, com ganho normalizado.
3. Transcreve **durante** a gravação, em pedaços de ~45 s cortados no silêncio
   mais próximo (VAD por energia). Ao clicar **Parar**, falta só o resto.
4. Saída em `Documentos\Dailys`:
   - `AAAA-MM-DD_HHMM_<nome>.txt` — texto com carimbos de tempo;
   - `AAAA-MM-DD_HHMM_<nome>.srt` — legenda com tempos;
   - `AAAA-MM-DD_HHMM_<nome>.wav` — áudio bruto (opção `manter_audio`).
5. Se um dispositivo faltar, o app continua com o outro e avisa na tela.
6. Se o app fechar no meio, o `.wav` permanece e, na próxima abertura, aparece
   **“Há uma gravação não transcrita”** com um botão **Transcrever**.

A pasta de saída é configurável pelo botão **Alterar pasta** (gravada em
`%APPDATA%\GravadorDaily\config.json`). Log em
`%LOCALAPPDATA%\GravadorDaily\log.txt`.

---

## Estrutura

```
src/gravador_daily/
  __main__.py        entrada (CLI, --selftest, --transcrever-arquivo)
  app.py             interface tkinter/ttk
  sessao.py          orquestra gravação + WAV + transcrição
  transcritor.py     faster-whisper, corte em silêncio, fila incremental
  audio/base.py      interface FonteAudio + fábrica por plataforma
  audio/windows.py   mic + loopback WASAPI (PyAudioWPatch)  [Windows-only]
  audio/arquivo.py   fonte de arquivo via ffmpeg (teste/Linux e mp3/mp4)
  audio/linux.py     microfone via sounddevice (desenvolvimento)
  mixagem.py         resampling, mono, mixagem, WAV
  saida.py           TXT e SRT
  config.py          config.json e caminhos do sistema
  log.py             log em arquivo
tests/               pytest (ver abaixo)
scripts/             baixar_modelo.py, gerar_wav_teste.py
gravador-daily.spec  PyInstaller (onedir, windowed)
.github/workflows/   build-windows.yml
```

---

## Uso em desenvolvimento (Linux)

```bash
python3 -m venv .venv            # ou: uv venv --python 3.12 .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

python scripts/baixar_modelo.py  # baixa o modelo small para modelos/small
pytest
```

Rodar a interface com um arquivo simulando a captura (não precisa de microfone):

```bash
python -m gravador_daily --fonte-arquivo caminho/fala.wav --acelerado --autoiniciar
```

Transcrever um arquivo direto, sem interface:

```bash
python -m gravador_daily --transcrever-arquivo reu.mp3
```

Smoke test do executável (a CI usa isto):

```bash
python lancador.py --selftest           # carrega o modelo e transcreve um WAV de 3 s
python -m gravador_daily --selftest --wav fala.wav
```

Gerar um áudio de teste em PT-BR (usa `edge-tts`, se disponível):

```bash
python scripts/gerar_wav_teste.py --saida fala.wav --repeticoes 7
```

### Testes

```bash
pytest                                  # tudo que roda no Linux sem modelo
pytest -m "not windows and not modelo"   # o que a CI roda antes de baixar o modelo
```

Marcadores: `windows` (só no Windows), `modelo` (exige `modelos/small`),
`audio_real` (reconhecimento de fala de verdade, lento).

---

## Empacotamento (GitHub Actions)

`.github/workflows/build-windows.yml`, no `windows-latest` com Python 3.11:

1. instala dependências e roda `pytest` (sem Windows/modelo);
2. baixa o modelo (`scripts/baixar_modelo.py`);
3. roda o selftest em desenvolvimento;
4. gera o executável (`pyinstaller gravador-daily.spec`) — onedir, sem console;
5. roda o smoke test `dist\GravadorDaily\GravadorDaily.exe --selftest`;
6. compacta em `GravadorDaily-windows.zip` e publica como artefato;
7. em tags `v*`, cria um GitHub Release com o zip.

Não usa segredos além do `GITHUB_TOKEN` automático.

---

## O que só pode ser validado no Windows

Estes pontos foram escritos com cuidado, mas **não foram executados neste
ambiente Linux** — a confirmar no Windows:

- **captura do loopback WASAPI** (`audio/windows.py`): escolha do dispositivo de
  saída padrão, mixagem mic+loopback com taxas diferentes, comportamento quando
  não há fone de ouvido (eco do som do sistema no microfone);
- **empacotamento PyInstaller**: coleta de `ctranslate2`/`onnxruntime`/`av`,
  bundling do ffmpeg e do modelo — o `.exe` não foi gerado nem executado aqui;
- **`PyAudioWPatch`**: instalado apenas no Windows (marcador de plataforma);
- **abertura de arquivos/pastas** (`os.startfile`) e o aviso do SmartScreen.

---

## LGPD

Grave apenas reuniões em que todos os participantes foram avisados.
