# Gravador de Daily — como usar

Um programinha que grava a sua reunião (a sua voz e o som que sai do
computador) e no final gera um **arquivo de texto com a conversa escrita**,
em português.

---

## 1. Baixar e descompactar

1. Baixe o arquivo **`GravadorDaily-windows.zip`**.
2. Clique com o botão direito e escolha **Extrair tudo…**.
3. Extraia para uma pasta fácil de achar, por exemplo
   **`C:\Users\<seu nome>\GravadorDaily`**.
4. Abra a pasta e dê dois cliques em **`GravadorDaily.exe`**.

> Não funciona abrir o `.exe` de dentro do arquivo `.zip`: extraia primeiro.

## 2. O aviso do Windows (SmartScreen)

Na primeira vez o Windows pode mostrar uma tela azul de aviso
("O Windows protegeu o seu PC"). Isso acontece porque o programa não é
assinado digitalmente.

1. Clique em **Mais informações**.
2. Clique em **Executar assim mesmo**.

Só precisa fazer isso uma vez.

## 3. Antes de gravar

- Confira o campo **Nome da reunião** (já vem escrito "Daily").
- Prefira usar **fone de ouvido**. Sem fone, o som que sai do computador pode
  voltar pelo microfone e sair repetido na transcrição.
- **Faça um teste de 30 segundos**: grave, pare, veja se o texto saiu coerente.

## 4. Gravar

1. Aperte o botão grande **● Gravar**. O botão vira **■ Parar** e o cronômetro
   começa a contar.
2. Duas barrinhas mostram o nível do **Microfone** e do **Som do computador** —
   se elas se mexem, está tudo certo.
3. Ao terminar a reunião, aperte **■ Parar**.
4. Espere a mensagem **"Transcrição salva em …"**. Em computadores mais simples
   isso pode levar um tempinho — quanto mais longa a reunião, mais demora.

> Se uma barra não se mexe, o programa avisa na área de Status (por exemplo,
> se não encontrou microfone). Ele continua gravando o que conseguiu.

## 5. Onde está o arquivo

Os arquivos ficam em **Documentos \ Dailys**, com nome no formato:

```
2026-11-11_0930_Daily.txt     <- o texto da reunião
2026-11-11_0930_Daily.srt     <- legenda com tempos
2026-11-11_0930_Daily.wav     <- o áudio gravado
```

- Use o botão **Abrir pasta** para ver a pasta.
- Use o botão **Abrir transcrição** para abrir o texto da última gravação.
- Para salvar em outro lugar, use **Alterar pasta** (escolha a pasta desejada).

## 6. Se o programa fechar no meio

Nada de pânico: o áudio já foi salvo. Ao abrir de novo, aparece
**"Há uma gravação não transcrita"** com um botão **Transcrever** — clique nele
e ele gera o texto a partir do áudio que ficou salvo.

## 7. Transcrever um áudio que você já tem

Clique em **Transcrever arquivo de áudio…** e escolha um
`.mp3`, `.wav`, `.m4a` ou `.mp4`. O texto e a legenda aparecem na pasta de saída.

## 8. Dicas

- Feche outros programas pesados durante a transcrição: ela usa bastante a
  memória e o processador.
- Grave apenas reuniões em que todos foram avisados de que a conversa está
  sendo gravada (LGPD).
- Se algo der errado, existe um registro em
  `%LOCALAPPDATA%\GravadorDaily\log.txt` que ajuda a entender o problema.
