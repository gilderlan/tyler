import argparse
import sys
import time
from pathlib import Path

from tyler import __version__, system
from tyler.ops import blur, cut, download, vertical, watermark
from tyler.report import PlainReporter, Reporter, RichReporter
from tyler.video import default_output


def _size(value: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in value.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use o formato LARGURAxALTURA, ex: 1080x1920")
    if w % 2 or h % 2:
        raise argparse.ArgumentTypeError("largura e altura precisam ser pares")
    return w, h


def _time(value: str) -> float:
    try:
        return cut.parse_time(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _position(value: str) -> str:
    try:
        return watermark.parse_position(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _reporter(args: argparse.Namespace) -> Reporter:
    if args.plain or not sys.stderr.isatty():
        return PlainReporter()
    return RichReporter(show_preview=not args.no_preview, show_system=not args.no_stats)


def main() -> None:
    parser = argparse.ArgumentParser(prog="tyler", description="Editor de vídeo comandado por IA. "
                                     "Sem comando, abre o modo conversa: peça as edições em português.")
    parser.add_argument("--version", action="version", version=f"tyler {__version__}")
    sub = parser.add_subparsers(dest="command", title="comandos")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plain", action="store_true", help="saída em texto simples, sem painel")
    common.add_argument("--no-preview", action="store_true", help="não mostra a miniatura do quadro no painel")
    common.add_argument("--no-stats", action="store_true", help="não mostra CPU, modelos e comando no painel")
    common.add_argument("--eco", action="store_true",
                        help="modo econômico: usa só os núcleos de eficiência; mais lento, esquenta menos")

    p = sub.add_parser("vertical", parents=[common], help="converte vídeo horizontal para vertical (9:16)")
    p.add_argument("input", type=Path, help="vídeo de entrada")
    p.add_argument("-o", "--output", type=Path, help="arquivo de saída (padrão: <nome>_tyler_vertical.mp4)")
    p.add_argument("-m", "--mode", choices=vertical.MODES, default="auto",
                   help="auto: segue os rostos | center: corte fixo no centro | fit: vídeo inteiro com fundo desfocado")
    p.add_argument("-s", "--size", type=_size, default=(1080, 1920), help="resolução final (padrão: 1080x1920)")

    p = sub.add_parser("blur", parents=[common], help="borra rostos e placas de veículos automaticamente")
    p.add_argument("input", type=Path, help="vídeo de entrada")
    p.add_argument("-o", "--output", type=Path, help="arquivo de saída (padrão: <nome>_tyler_blur.mp4)")
    p.add_argument("-t", "--targets", choices=blur.TARGETS, default="all",
                   help="all: rostos e placas | faces: só rostos | plates: só placas")
    p.add_argument("--style", choices=blur.STYLES, default="blur",
                   help="blur: desfoque | pixel: mosaico | black: tarja preta")

    p = sub.add_parser("cut", parents=[common], help="corta um trecho do vídeo entre dois tempos")
    p.add_argument("input", type=Path, help="vídeo de entrada")
    p.add_argument("start", type=_time, help="início: segundos (90), MM:SS (1:30) ou HH:MM:SS (1:02:03)")
    p.add_argument("end", type=_time, nargs="?", help="fim, no mesmo formato (padrão: até o final do vídeo)")
    p.add_argument("-o", "--output", type=Path, help="arquivo de saída (padrão: <nome>_tyler_cut.mp4)")
    p.add_argument("--copy", action="store_true",
                   help="não recodifica: instantâneo e sem perda, mas o início cai no quadro-chave anterior")

    p = sub.add_parser("watermark", parents=[common], help="coloca uma imagem (logo) como marca d'água")
    p.add_argument("input", type=Path, help="vídeo de entrada")
    p.add_argument("image", type=Path, help="imagem da marca (PNG com transparência, JPG ou WebP)")
    p.add_argument("-o", "--output", type=Path, help="arquivo de saída (padrão: <nome>_tyler_watermark.mp4)")
    p.add_argument("-p", "--position", type=_position, default="bottom-right",
                   help=f"{', '.join(watermark.POSITIONS)} (padrão: bottom-right; aceita também right-down etc.)")
    p.add_argument("-s", "--size", type=float, default=20,
                   help="largura da marca em %% do lado menor do vídeo (padrão: 20)")
    p.add_argument("--opacity", type=float, default=1.0, help="opacidade de 0.1 a 1 (padrão: 1, sem transparência)")
    p.add_argument("--margin", type=float, default=3, help="distância da borda em %% do lado menor (padrão: 3)")

    p = sub.add_parser("download", parents=[common], help="baixa vídeo ou áudio do YouTube (e outros sites)")
    p.add_argument("url", help="link do vídeo")
    p.add_argument("-o", "--output",  # texto, não Path: "pasta/" precisa manter a barra final
                   help="arquivo ou pasta de saída (padrão: <título do vídeo>.mp4 na pasta atual)")
    p.add_argument("-a", "--only-audio", action="store_true", help="baixa só o áudio")
    p.add_argument("--audio-format", choices=download.AUDIO_FORMATS, default="m4a",
                   help="m4a: áudio original, sem recodificar | mp3: converte (192 kbps)")

    args = parser.parse_args()
    if args.command is None:
        from tyler import agent  # importa o SDK da Anthropic só no modo conversa
        agent.main()
        return

    if args.command == "download":
        if not args.url.startswith(("http://", "https://")):
            sys.exit(f"Link inválido: {args.url} (use o endereço completo, com https://)")
        output = partial = None  # o nome só é conhecido depois do download, que limpa os próprios temporários
    else:
        for path in (args.input, getattr(args, "image", None)):
            if path is not None and not path.exists():
                sys.exit(f"Arquivo não encontrado: {path}")
        output = partial = args.output or default_output(args.input, args.command)
        if output.resolve() == args.input.resolve():
            sys.exit("A saída não pode ser o próprio vídeo de entrada.")

    if args.eco:
        system.enable_eco()
    started = time.monotonic()
    try:
        with _reporter(args) as reporter:
            if args.command == "vertical":
                vertical.run(args.input, output, args.mode, args.size, reporter)
            elif args.command == "blur":
                blur.run(args.input, output, args.targets, args.style, reporter)
            elif args.command == "cut":
                cut.run(args.input, output, args.start, args.end, args.copy, reporter)
            elif args.command == "watermark":
                watermark.run(args.input, args.image, output, args.position, args.size, args.opacity, args.margin,
                              reporter)
            elif args.command == "download":
                output = download.run(args.url, args.output, args.only_audio, args.audio_format, reporter)
            reporter.done(output, time.monotonic() - started)
    except KeyboardInterrupt:
        if partial:
            partial.unlink(missing_ok=True)
        print("\nCancelado. Nenhum arquivo foi gerado.", file=sys.stderr)
        sys.exit(130)
    except (download.DownloadFailed, cut.InvalidRange, watermark.InvalidWatermark, system.MissingTool) as e:
        if partial:
            partial.unlink(missing_ok=True)
        sys.exit(str(e))
    except Exception:
        if partial:
            partial.unlink(missing_ok=True)  # não deixa vídeo pela metade para trás
        raise
    print(output)


if __name__ == "__main__":
    main()
