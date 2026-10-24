# Tyler

[English](README.md) · **Português**

```text
████████╗██╗   ██╗██╗     ███████╗██████╗
╚══██╔══╝╚██╗ ██╔╝██║     ██╔════╝██╔══██╗
   ██║    ╚████╔╝ ██║     █████╗  ██████╔╝
   ██║     ╚██╔╝  ██║     ██╔══╝  ██╔══██╗
   ██║      ██║   ███████╗███████╗██║  ██║
   ╚═╝      ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
  a primeira regra do Tyler: você não
  sobrescreve o vídeo original.
```

Editor de vídeo comandado por IA: um plugin do Claude Code que roda localmente no macOS e no Linux.

> Nome inspirado no Tyler Durden (*Clube da Luta*), o projecionista que mexia nos filmes quadro a quadro.

## Objetivo

Editar vídeos pedindo em linguagem natural ao Claude Code, por exemplo:

- "converte esse vídeo para vertical seguindo a pessoa"
- "borra todos os rostos e placas de carro"
- "baixa esse vídeo do YouTube"
- "corta do 1:30 até o 2:45"
- "coloca meu logo no canto inferior direito"

## Instalação

1. Instale os programas que o Tyler usa: uv, ffmpeg (versão 7 ou mais nova recomendada) e deno.

   macOS:

   ```bash
   brew install uv ffmpeg deno
   ```

   Linux (Debian/Ubuntu; em outras distribuições, use o gerenciador de pacotes delas para o ffmpeg):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   sudo apt install ffmpeg
   curl -fsSL https://deno.land/install.sh | sh
   ```

   Algumas distribuições trazem um ffmpeg mais antigo (o Debian 12 tem o 5.1, o Ubuntu 24.04 tem o 6.1). Funciona,
   mas o corte rápido (`--copy`) pode sair alguns décimos de segundo maior. Para ter o ffmpeg 7 nelas, use uma
   [versão estática](https://johnvansickle.com/ffmpeg/).

2. Instale o plugin no [Claude Code](https://code.claude.com):

   ```bash
   claude plugin marketplace add gilderlan/tyler
   claude plugin install tyler@tyler
   ```

A primeira operação demora mais, porque o `uv` monta o ambiente Python dentro do plugin.
Para receber versões novas: `claude plugin marketplace update tyler`.

## Uso

Em qualquer pasta, peça ao Claude Code em português ("deixa o video.mp4 vertical", "borra as placas do rua.mp4")
ou chame a skill direto:

| Skill | O que faz |
|---|---|
| `/tyler:vertical ~/Movies/video.mp4` | Horizontal → 9:16 seguindo os rostos (ou corte no centro, ou vídeo inteiro com fundo desfocado) |
| `/tyler:blur ~/Movies/rua.mp4` | Borra rostos e/ou placas, com desfoque, mosaico ou tarja preta |
| `/tyler:cut ~/Movies/video.mp4 1:30 2:45` | Corta um trecho entre dois tempos |
| `/tyler:watermark ~/Movies/video.mp4 ~/logo.png` | Coloca um logo num canto ou no centro |
| `/tyler:download <link>` | Baixa vídeo ou áudio do YouTube, Instagram, TikTok, Vimeo... |

Cada operação gera um arquivo novo ao lado do original (`<nome>_tyler_<operação>.<ext>`); o original nunca é alterado.
O `download` salva com o título do vídeo e nunca sobrescreve um arquivo existente. O vídeo sai em H.264 + AAC
quando o site oferece, o que no YouTube limita a 1080p. Baixe só vídeos seus, com licença livre ou com autorização do autor.

## Arquitetura

```
 Claude Code ── skills/ (/tyler:cut, /tyler:vertical, ...)
                   │  só orquestram: chamam a CLI
           ┌───────▼────────┐
           │   CLI tyler    │  src/tyler/cli.py
           └───────┬────────┘
           ┌───────▼────────┐
           │ src/tyler/ops  │  ← lógica única de cada operação
           └───────┬────────┘
          ┌────────┴────────┐
       ffmpeg         modelos de IA
                     (rostos, placas)
```

Toda operação vive em `src/tyler/ops/` e é exposta pela CLI `tyler`, o motor que as skills chamam com
`uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <comando>`. Nenhuma lógica fica nas skills.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `src/tyler/` | Biblioteca Python e CLI |
| `src/tyler/ops/` | Uma operação por módulo (reframe, blur, ...) |
| `skills/` | Skills do Claude Code (`/tyler:vertical`, `/tyler:blur`, ...) |
| `.claude-plugin/` | Manifesto do plugin e do marketplace |
| `models/` | Modelos de IA baixados (fora do git) |
| `samples/` | Vídeos de teste (fora do git) |
| `tests/` | Testes |

## Desenvolvimento

Carregue o plugin direto desta pasta, sem instalar: `claude --plugin-dir .` (depois de editar uma skill,
`/reload-plugins`). Antes de publicar, rode `claude plugin validate .`. Testes: `uv run pytest`.

Requisitos: macOS (Apple Silicon) ou Linux, [uv](https://docs.astral.sh/uv/) com Python 3.12,
ffmpeg 7 ou mais novo e deno (usado pelo yt-dlp para baixar do YouTube). Se faltar algum, o Tyler avisa e diz como instalar.

### CLI

As skills chamam a CLI, que também pode ser usada direto para testar uma operação:

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

No rodapé do painel aparecem o uso de CPU e RAM (do Tyler e dos ffmpeg que ele abre), o estado térmico do Mac (só no macOS),
os modelos de IA em uso (inferências e tempo médio) e o comando que está rodando. `--no-stats` esconde o rodapé.

Para esquentar menos, use `--eco`: o Tyler e o ffmpeg passam a rodar em segundo plano, nos núcleos de eficiência
(no Linux, com prioridade mais baixa).
Fica cerca de 3x mais lento.

## Modelos de IA

| Uso | Modelo | Onde fica |
|---|---|---|
| Rostos | YuNet (OpenCV Zoo) | `models/` |
| Placas | YOLOv9 do [open-image-models](https://github.com/ankandrew/open-image-models) | `~/.cache/open-image-models/` |

São baixados automaticamente no primeiro uso. Nos chips da Apple o modelo de placas roda no CoreML, cerca de 6x mais
rápido; no Linux ele roda na CPU, então borrar placas demora mais.

## Roadmap

- [x] `vertical` — horizontal → 9:16 com enquadramento inteligente
- [x] `blur` — blur automático de rostos e placas
- [x] `cut` — corta um trecho entre dois tempos
- [x] `watermark` — marca d'água com imagem
- [x] `download` — baixa vídeo ou áudio do YouTube e outros sites
- [ ] Ações Rápidas no Finder
- [ ] Interface web

## Como contribuir

Contribuições são bem-vindas: correções, novas operações, skills melhores ou traduções.

**Primeiros passos** (com uv, ffmpeg e deno instalados, como em [Instalação](#instalação)):

```bash
git clone https://github.com/gilderlan/tyler.git
cd tyler
uv sync
uv run pytest
claude --plugin-dir .   # Claude Code com a sua cópia local do plugin
```

**Regras do projeto** (também no `CLAUDE.md`, que o Claude Code lê automaticamente):

- A lógica de vídeo fica só em `src/tyler/ops/`, um módulo por operação, exposto como subcomando da CLI `tyler`.
  As skills só orquestram: chamam a CLI e nunca reimplementam lógica.
- As operações nunca imprimem direto: recebem um `Reporter` (`src/tyler/report.py`) e reportam por ele as etapas,
  estatísticas e prévias.
- Use o ffmpeg para codificar e decodificar, preserve o áudio original sempre que possível e nunca sobrescreva a
  entrada: a saída padrão é `<nome>_tyler_<operação>.<ext>`, ao lado do original.
- Se a operação usa um programa do sistema, confira com `system.require()` logo no início, para que a falta dele
  vire uma mensagem clara em vez de um traceback.
- Idiomas: skills, manifestos e `README.md` em inglês; mensagens da CLI, comentários do código e `README.pt-BR.md`
  em português. Ao mudar o README, atualize as duas versões.

**Adicionando uma operação**

1. Crie `src/tyler/ops/<operação>.py` com uma função `run(...)` que recebe um `Reporter`.
2. Acrescente o subcomando em `src/tyler/cli.py`.
3. Escreva testes em `tests/test_<operação>.py`, gerando vídeos pequenos com o ffmpeg (veja `tests/test_cut.py`).
4. Crie `skills/<operação>/SKILL.md` chamando `uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <operação>`.
5. Documente nos dois READMEs.

**Antes de abrir um pull request**

- `uv run pytest` passa. Os testes de download precisam de internet e são pulados sem ela. O teste de placas com
  foto real precisa de `samples/car.png` (qualquer foto de carro com a placa visível; ela não vai no git) e é pulado sem ela.
- `claude plugin validate .` passa.
- Você testou a mudança no Claude Code com `claude --plugin-dir .`.
- Um assunto por pull request, descrevendo o que mudou e como você testou.

**Relatando um problema:** [abra uma issue](https://github.com/gilderlan/tyler/issues) com o seu sistema (macOS ou a distribuição Linux), a saída de
`ffmpeg -version | head -1`, o comando ou pedido que você fez e a mensagem de erro completa.

## Licença

[MIT](LICENSE) © 2026 Gilderlan Braz
