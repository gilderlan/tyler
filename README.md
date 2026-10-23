# Tyler

Editor de vídeo comandado por IA, rodando localmente no Mac.

> Nome inspirado no Tyler Durden (*Clube da Luta*), o projecionista que mexia nos filmes quadro a quadro.

## Objetivo

Editar vídeos dando comandos em linguagem natural, por exemplo:

- "converte esse vídeo para vertical seguindo a pessoa"
- "borra todos os rostos e placas de carro"
- "baixa esse vídeo do YouTube"
- "corta do 1:30 até o 2:45"
- "coloca meu logo no canto inferior direito"

## Arquitetura

```
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ Skills (/cmd)│  │  CLI tyler   │  │ Web UI (futuro)  │
└──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
       └─────────────────┼───────────────────┘
                 ┌───────▼────────┐
                 │  src/tyler/ops │  ← lógica única de cada operação
                 └───────┬────────┘
          ┌──────────────┼──────────────┐
       ffmpeg      modelos de IA     IA de decisão
                 (rostos, placas)   (o que fazer/onde)
```

Toda operação vive em `src/tyler/ops/` e é exposta pela CLI `tyler`.
As skills do Claude Code e a futura interface web apenas chamam a CLI/biblioteca,
assim nenhuma lógica fica duplicada.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `src/tyler/` | Biblioteca Python e CLI |
| `src/tyler/ops/` | Uma operação por módulo (reframe, blur, ...) |
| `.claude/skills/` | Skills do Claude Code (`/vertical`, `/blur`, ...) |
| `models/` | Modelos de IA baixados (fora do git) |
| `samples/` | Vídeos de teste (fora do git) |
| `tests/` | Testes |

## Requisitos

- macOS (Apple Silicon)
- [uv](https://docs.astral.sh/uv/) e Python 3.12
- ffmpeg (`brew install ffmpeg`)
- deno (`brew install deno`), usado pelo yt-dlp para baixar do YouTube

## Uso

```bash
uv sync
uv run tyler --help

# horizontal → vertical seguindo os rostos
uv run tyler vertical video.mp4
# corte fixo no centro / vídeo inteiro com fundo desfocado
uv run tyler vertical video.mp4 --mode center
uv run tyler vertical video.mp4 --mode fit

# borra rostos e placas (ou só um deles) com desfoque, mosaico ou tarja preta
uv run tyler blur video.mp4
uv run tyler blur video.mp4 --targets plates --style pixel

# corta um trecho: segundos, MM:SS ou HH:MM:SS; sem o fim, vai até o final
uv run tyler cut video.mp4 1:30 2:45
uv run tyler cut video.mp4 1:30 --copy   # instantâneo, sem recodificar (início no quadro-chave anterior)

# marca d'água: posição, tamanho (% do lado menor do vídeo) e opacidade
uv run tyler watermark video.mp4 logo.png                      # canto inferior direito, 20%
uv run tyler watermark video.mp4 logo.png -p top-left --size 10 --opacity 0.6

# baixa do YouTube (e Instagram, TikTok, Vimeo...): vídeo em mp4 ou só o áudio
uv run tyler download https://www.youtube.com/watch?v=jNQXAC9IVRw
uv run tyler download --only-audio <link>                      # m4a, sem recodificar
uv run tyler download --only-audio --audio-format mp3 <link> -o musicas/
```

O `download` usa o [yt-dlp](https://github.com/yt-dlp/yt-dlp), salva com o título do vídeo na pasta atual
(ou no arquivo/pasta de `-o`) e nunca sobrescreve um arquivo existente. O vídeo sai em H.264 + AAC quando o site
oferece, o que no YouTube limita a 1080p. Baixe só vídeos seus, com licença livre ou com autorização do autor.

No terminal, a CLI mostra um painel ao vivo com as etapas, a barra de progresso, o tempo restante,
as estatísticas (rostos, placas, cortes de cena) e uma miniatura do quadro que está sendo analisado,
com as detecções desenhadas. Use `--no-preview` para esconder a miniatura e `--plain` para saída em texto simples
(que também é usada automaticamente quando a saída não é um terminal, por exemplo nas skills).
Ctrl+C cancela e apaga o vídeo incompleto.

No rodapé do painel aparecem o uso de CPU e RAM (do Tyler e dos ffmpeg que ele abre), o estado térmico do Mac,
os modelos de IA em uso (inferências e tempo médio) e o comando que está rodando. `--no-stats` esconde o rodapé.

Para esquentar menos, use `--eco`: o Tyler e o ffmpeg passam a rodar em segundo plano, nos núcleos de eficiência.
Fica cerca de 3x mais lento.

No Claude Code (aberto na pasta do projeto): `/vertical ~/Movies/video.mp4`, `/blur ~/Movies/rua.mp4`, `/cut ~/Movies/video.mp4 1:30 2:45`, `/watermark ~/Movies/video.mp4 ~/logo.png`, `/download <link>`

## Modelos de IA

| Uso | Modelo | Onde fica |
|---|---|---|
| Rostos | YuNet (OpenCV Zoo) | `models/` |
| Placas | YOLOv9 do [open-image-models](https://github.com/ankandrew/open-image-models) | `~/.cache/open-image-models/` |

São baixados automaticamente no primeiro uso.

## Roadmap

- [x] `vertical` — horizontal → 9:16 com enquadramento inteligente
- [x] `blur` — blur automático de rostos e placas
- [x] `cut` — corta um trecho entre dois tempos
- [x] `watermark` — marca d'água com imagem
- [x] `download` — baixa vídeo ou áudio do YouTube e outros sites
- [ ] Ações Rápidas no Finder
- [ ] Interface web
