"""Converte vídeo horizontal para vertical (9:16).

Modos:
- auto:   recorta 9:16 seguindo os rostos, com movimento de câmera suave e cortes de cena respeitados.
- center: recorta 9:16 fixo no centro.
- fit:    mantém o quadro inteiro, com o próprio vídeo desfocado preenchendo o fundo.
"""

from pathlib import Path

import cv2
import numpy as np

from tyler import models, system
from tyler.report import FACE_MODEL, GREEN, PlainReporter, Reporter, decoding, draw_boxes, shell_command
from tyler.video import FrameWriter, VideoInfo, default_output, encode_args, frames, probe, run_ffmpeg

MODES = ("auto", "center", "fit")
RATIO = 9 / 16
SAMPLES_PER_SECOND = 5
ANALYSIS_WIDTH = 640  # quadros são reduzidos para detectar rostos mais rápido
SCENE_CUT_THRESHOLD = 0.6  # correlação de histograma abaixo disso = corte de cena
DEADZONE = 0.08  # fração da largura do recorte que o rosto pode andar sem a câmera se mexer
SMOOTH_SECONDS = 0.5
MAX_GAP_SECONDS = 1.5  # sem rosto por mais tempo que isso, o recorte volta para o centro
MAX_JUMP = 0.15  # fração da largura: detecção sem vizinha a essa distância é tratada como falso positivo

ANALYZE_STEP = "Analisando rostos e cortes de cena"
RENDER_STEP = "Gerando vídeo vertical"


def run(input_path: Path, output: Path | None = None, mode: str = "auto", size: tuple[int, int] = (1080, 1920),
        reporter: Reporter | None = None) -> Path:
    system.require(*system.VIDEO_TOOLS)
    if mode not in MODES:
        raise ValueError(f"Modo inválido: {mode}. Use um de: {', '.join(MODES)}")
    output = output or default_output(input_path, "vertical")
    reporter = reporter or PlainReporter()
    info = probe(input_path)
    if info.width / info.height <= RATIO + 0.01:
        mode = "fit"  # já é vertical (ou mais estreito): só ajusta ao tamanho final

    reporter.header(f"vertical ({mode}) · {input_path.name}", info.describe())
    if mode == "auto":
        reporter.plan([ANALYZE_STEP, RENDER_STEP])
        _run_auto(input_path, output, size, info, reporter)
    else:
        with reporter.step("Convertendo com ffmpeg", round(info.duration * info.fps)) as step:
            run_ffmpeg(["-i", str(input_path), "-vf", _filter(mode, size), *encode_args(output)],
                       on_frame=step.update, on_start=lambda cmd: reporter.command(shell_command(cmd)))
    return output


def _filter(mode: str, size: tuple[int, int]) -> str:
    w, h = size
    if mode == "center":
        return f"crop=trunc(ih*{RATIO}/2)*2:ih,scale={w}:{h},setsar=1"
    return (
        f"split[a][b];"
        f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3,eq=brightness=-0.08[bg];"
        f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def _run_auto(input_path: Path, output: Path, size: tuple[int, int], info: VideoInfo, reporter: Reporter) -> None:
    sample_frames, centers, scenes, total, (frame_w, frame_h) = _analyze(input_path, info, reporter)
    crop_w = int(frame_h * RATIO) // 2 * 2
    xs = camera_path(sample_frames, centers, scenes, total, frame_w, crop_w)

    on_start = lambda cmd: reporter.command(shell_command(cmd))  # noqa: E731
    with (reporter.step(RENDER_STEP, total) as step,
          FrameWriter(output, *size, info.fps, audio_from=input_path, on_start=on_start) as writer):
        for i, frame in enumerate(frames(input_path)):
            x = xs[min(i, total - 1)]
            crop = frame[:, x : x + crop_w]
            writer.write(cv2.resize(crop, size, interpolation=cv2.INTER_LANCZOS4))
            step.update(i + 1, preview=lambda: _crop_preview(frame, x, crop_w))


def _crop_preview(frame: np.ndarray, x: int, crop_w: int) -> np.ndarray:
    """Quadro original escurecido, com a janela 9:16 que vai para o vídeo em destaque."""
    out = draw_boxes(frame, [(x, 0, x + crop_w, frame.shape[0], GREEN)])
    scale = out.shape[1] / frame.shape[1]
    x1, x2 = int(x * scale), int((x + crop_w) * scale)
    out[:, :x1] //= 3
    out[:, x2:] //= 3
    return out


def _analyze(input_path: Path, info: VideoInfo, reporter: Reporter) -> tuple:
    """Percorre o vídeo detectando rostos e cortes de cena em ~5 amostras por segundo."""
    step_size = max(1, round(info.fps / SAMPLES_PER_SECOND))
    detector = None
    sample_frames, centers, scenes = [], [], []
    scene, prev_hist = 0, None
    with_face = 0
    total = 0
    frame_w = frame_h = 0

    with reporter.step(ANALYZE_STEP, round(info.duration * info.fps)) as step:
        reporter.command(decoding(input_path, info))
        for i, frame in enumerate(frames(input_path)):
            total += 1
            if i % step_size:
                continue
            if detector is None:
                frame_h, frame_w = frame.shape[:2]
                scale = ANALYSIS_WIDTH / frame_w
                small_size = (ANALYSIS_WIDTH, round(frame_h * scale))
                detector = cv2.FaceDetectorYN.create(str(models.yunet()), "", small_size, 0.7)
            small = cv2.resize(frame, small_size, interpolation=cv2.INTER_AREA)

            hist = cv2.calcHist([cv2.cvtColor(small, cv2.COLOR_BGR2HSV)], [0, 1], None, [50, 60], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < SCENE_CUT_THRESHOLD:
                scene += 1
            prev_hist = hist

            with reporter.inference(FACE_MODEL):
                _, faces = detector.detect(small)
            boxes = [] if faces is None else [f[:4] / scale for f in faces]
            with_face += bool(boxes)
            sample_frames.append(i)
            centers.append(subject_center(boxes, int(frame_h * RATIO)))
            scenes.append(scene)
            step.update(
                i + 1,
                stats={"amostras com rosto": f"{with_face}/{len(sample_frames)}", "cortes de cena": scene},
                preview=lambda: draw_boxes(small, [(x, y, x + w, y + h, GREEN) for x, y, w, h in (b * scale for b in boxes)]),
            )
    if total == 0:
        raise ValueError(f"Nenhum quadro lido de {input_path}")
    return sample_frames, centers, scenes, total, (frame_w, frame_h)


def subject_center(boxes: list, crop_w: int) -> float | None:
    """Centro horizontal a enquadrar: todos os rostos se couberem no recorte, senão o maior."""
    if not boxes:
        return None
    left = min(b[0] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    if right - left <= crop_w * 0.9:
        return (left + right) / 2
    x, _, w, _ = max(boxes, key=lambda b: b[2] * b[3])
    return x + w / 2


def camera_path(sample_frames, centers, scenes, total, frame_w, crop_w) -> np.ndarray:
    """Transforma os centros detectados em uma posição x de recorte por quadro.

    Cada cena é tratada separadamente (a câmera "pula" no corte em vez de deslizar),
    detecções isoladas são descartadas como falsos positivos, lacunas curtas sem rosto são
    interpoladas e lacunas longas voltam para o centro. O movimento passa por zona morta +
    suavização para parecer um operador de câmera e não tremer.
    """
    sample_frames = np.asarray(sample_frames)
    scenes = np.asarray(scenes)
    xs = np.empty(total, dtype=int)
    starts = [0] + [sample_frames[k] for k in range(1, len(scenes)) if scenes[k] != scenes[k - 1]] + [total]
    window = max(1, round(SMOOTH_SECONDS * SAMPLES_PER_SECOND))
    max_gap = round(MAX_GAP_SECONDS * SAMPLES_PER_SECOND)

    for seg, scene_id in enumerate(np.unique(scenes)):
        idx = np.flatnonzero(scenes == scene_id)
        values = np.array([np.nan if centers[k] is None else centers[k] for k in idx], dtype=float)
        values = _drop_isolated(values, MAX_JUMP * frame_w)
        values, is_default = _fill_gaps(values, max_gap, frame_w / 2)

        values = _median(values, 5)
        values = _deadzone(values, DEADZONE * crop_w, exact=is_default)
        values = _gaussian(values, window)

        f0, f1 = starts[seg], starts[seg + 1]
        cx = np.interp(np.arange(f0, f1), sample_frames[idx], values)
        xs[f0:f1] = np.clip(np.round(cx - crop_w / 2), 0, frame_w - crop_w)
    return xs


def _drop_isolated(values: np.ndarray, max_jump: float) -> np.ndarray:
    """Descarta detecções sem uma vizinha (amostra anterior ou seguinte) perto delas."""
    out = values.copy()
    for k, v in enumerate(values):
        if np.isnan(v):
            continue
        neighbors = values[max(0, k - 1) : k + 2]
        if sum(abs(n - v) <= max_jump for n in neighbors if not np.isnan(n)) < 2:  # conta ela mesma
            out[k] = np.nan
    return out


def _fill_gaps(values: np.ndarray, max_gap: int, default: float) -> tuple[np.ndarray, np.ndarray]:
    """Preenche amostras sem rosto: lacunas curtas são interpoladas/mantidas, longas voltam para `default`.

    Retorna também quais amostras receberam `default`.
    """
    out = values.copy()
    is_default = np.zeros(len(values), dtype=bool)
    n = len(values)
    k = 0
    while k < n:
        if not np.isnan(values[k]):
            k += 1
            continue
        end = k
        while end < n and np.isnan(values[end]):
            end += 1
        before = values[k - 1] if k > 0 else np.nan
        after = values[end] if end < n else np.nan
        if end - k > max_gap or (np.isnan(before) and np.isnan(after)):
            out[k:end] = default
            is_default[k:end] = True
        elif np.isnan(before) or np.isnan(after):
            out[k:end] = after if np.isnan(before) else before
        else:
            out[k:end] = np.linspace(before, after, end - k + 2)[1:-1]
        k = end
    return out, is_default


def _median(values: np.ndarray, k: int) -> np.ndarray:
    pad = np.pad(values, k // 2, mode="edge")
    return np.array([np.median(pad[i : i + k]) for i in range(len(values))])


def _deadzone(values: np.ndarray, zone: float, exact: np.ndarray) -> np.ndarray:
    """Câmera só se move quando o alvo sai da zona; onde `exact`, vai direto ao alvo (volta ao centro)."""
    out = np.empty_like(values)
    cam = values[0]
    for i, v in enumerate(values):
        if exact[i]:
            cam = v
        elif abs(v - cam) > zone:
            cam = v - np.sign(v - cam) * zone
        out[i] = cam
    return out


def _gaussian(values: np.ndarray, sigma: float) -> np.ndarray:
    radius = int(3 * sigma)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    return np.convolve(np.pad(values, radius, mode="edge"), kernel, mode="valid")
