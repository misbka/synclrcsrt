# Letra em Vídeo

**Áudio + letra → `.lrc` → `.srt` → `.ass` animado → vídeo `.mp4`**

Aplicação local (sem instalação, sem dependências de pip) que transforma uma música e a letra
em um vídeo com legendas sincronizadas e animadas. Tudo roda no seu computador: um servidor
Python de arquivos simples serve a interface, e o **ffmpeg** faz a renderização final.

Feita apenas com a **biblioteca padrão do Python (3.8+)** e um `index.html` único
(HTML + CSS + JS, sem build, sem frameworks).

---

## Como rodar

**Windows**

```bat
iniciar.bat
```

**Linux / macOS**

```sh
sh iniciar.sh
# ou
python3 app.py
```

O servidor sobe em `http://127.0.0.1:8765/` (porta avança automaticamente se estiver ocupada)
e abre o navegador sozinho. **Feche a janela do terminal para encerrar.**

### Requisitos

| O que | Onde |
|---|---|
| Python 3.8 ou superior | [python.org](https://www.python.org/downloads/) |
| `ffmpeg` (+ `ffprobe`) | pasta `ffmpeg/` do projeto — já vem com os binários para Windows; em Linux/macOS, coloque o binário em `ffmpeg/` ou instale no sistema |

> O app procura o ffmpeg em `ffmpeg/`, `ffmpeg/bin/` e, por último, no `PATH`.
> Sem ele, a interface abre, mas a geração do vídeo falha.

---

## O fluxo em 4 etapas

A interface tem uma barra lateral com as etapas 1 → 4:

1. **Áudio e letra** — escolha (ou arraste) o arquivo de áudio e cole a letra,
   **um verso por linha**. Linhas em branco são ignoradas. Também dá para importar
   um `.lrc` existente. O vídeo final recebe o mesmo nome do áudio.
2. **Sincronizar** — toque o áudio e marque cada linha no instante certo.
   Um botão grande + atalhos de teclado marcam os tempos; a *compensação de reação*
   (padrão 150 ms) corrige o atraso do seu clique. Dá para voltar linha, ajustar o
   tempo manualmente, mexer na lista linha a linha e zerar as marcações.
3. **Estilo e fundo** — fonte (as da pasta `fontes/` aparecem na lista, com prévia),
   tamanho, cores, contorno, negrito, posição (topo/centro/base), margem, animações de
   entrada e saída (fade, subir, descer, zoom, pop) com duração em ms, fundo sólido ou
   imagem (preencher/caber inteira), resolução e prévia ao vivo que responde ao play do áudio.
4. **Gerar vídeo** — revê/edita o `.LRC`, baixa `.lrc` e `.srt`, ajusta duração máxima
   por linha, deslocamento global das legendas e FPS (24/30/60), e gera o `.mp4`
   com barra de progresso, log, botão de cancelar e atalho para abrir a pasta de saída.

### Atalhos do teclado (etapa 2)

| Tecla | Ação |
|---|---|
| <kbd>Espaço</kbd> | marcar linha |
| <kbd>B</kbd> | voltar uma linha |
| <kbd>K</kbd> | tocar / pausar |
| <kbd>J</kbd> | −5 s |
| <kbd>L</kbd> | +5 s |

O player fixo no rodapé tem play, ±5 s, barra de progresso e velocidade (0,5× a 1,25×).

---

## Estrutura de pastas

```
lrc_srt2/
├── app.py          # servidor HTTP + pipeline de renderização (stdlib only)
├── index.html      # interface inteira (HTML/CSS/JS)
├── iniciar.bat     # Windows
├── iniciar.sh      # Linux/macOS
├── ffmpeg/         # binários do ffmpeg
├── fontes/         # (opcional) .ttf/.otf próprios, usados na prévia e no vídeo
├── temp/           # uploads e arquivos temporários (limpo a cada início)
└── vídeos/         # resultado: <nome do áudio>.mp4 + .lrc + .srt
```

---

## Como funciona por dentro

1. O áudio enviado é convertido para **WAV PCM 48 kHz** e é *esse* arquivo que o
   navegador toca e que o ffmpeg usa — assim o tempo marcado na sincronização é idêntico
   ao do vídeo (MP3 VBR e atraso de encoder fariam navegador e ffmpeg divergirem).
2. As marcações viram `.lrc`; o `.lrc` é transformado em `.srt`
   (respeitando a duração máxima de cada linha).
3. O `.srt` vira um `.ass` animado: cada linha é dividida em segmentos de
   *entrada* → *estático* → *saída*, com tags `\fad`, `\move`, `\fscx/\fscy` etc.
   Os tamanhos são escalados a partir de uma referência 1080p, então a fonte renderiza
   igual em 480p, 720p, 1080p, vertical ou quadrado.
4. O ffmpeg grava o vídeo com `libx264` (CRF 20) + áudio AAC 192k,
   `+faststart`, sobre cor sólida ou imagem de fundo, com as fontes da pasta `fontes/`.

---

## API local

Útil para automatizar ou integrar:

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | a interface |
| GET | `/api/info` | caminho e versão do ffmpeg, pasta de saída |
| GET | `/api/fonts` | fontes da pasta `fontes/` |
| GET | `/api/job?id=` | estado de um job (`running`, `done`, `error`, `cancelled`) |
| POST | `/api/upload?kind=audio&name=` | envia áudio (convertido para WAV) ou imagem |
| POST | `/api/render` | inicia a renderização (JSON: áudio, lrc/srt, estilo, fundo, resolução, fps) |
| POST | `/api/cancel` | cancela o job em andamento |
| POST | `/api/open-folder` | abre a pasta `vídeos/` no explorador |

O servidor escuta apenas em `127.0.0.1` (local).

---

## Solução de problemas

- **“ffmpeg não encontrado”** — coloque `ffmpeg` (+ `ffprobe`) em `ffmpeg/` ou no `PATH`.
- **“Nenhuma legenda para gravar”** — sincronize ao menos uma linha na etapa 2.
- **Áudio “não está mais no servidor”** — o `temp/` é limpo a cada início; selecione o arquivo de novo.
- **Letra no vídeo “atrasada/adiantada”** — use a *compensação de reação* na etapa 2
  e/ou o deslocamento global de legendas na etapa 4.
- **Porta 8765 ocupada** — o app sobe automaticamente nas 20 portas seguintes.

## Licença

Sem licença definida até o momento — adicione um arquivo `LICENSE` se for publicar no GitHub.
