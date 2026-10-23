"""Anonimiza vídeos: borra rostos e placas de veículos automaticamente.

Funciona em duas passadas: primeiro detecta rostos/placas em todos os quadros,
depois aplica o efeito. Cada detecção também cobre alguns quadros vizinhos (antes e
depois), para o efeito não "piscar" quando o detector falha em um quadro isolado.
"""

import logging
import warnings
from pathlib import Path

import cv2
import numpy as np

from tyler import models, system
from tyler.report import FACE_MODEL, GREEN, YELLOW, PlainReporter, Reporter, decoding, draw_boxes, shell_command
from tyler.video import FrameWriter, VideoInfo, default_output, frames, probe

TARGETS = ("all", "faces", "plates")
STYLES = ("blur", "pixel", "black")

FACE_DETECT_WIDTH = 1280  # resolução usada na detecção de rostos (maior = acha rostos menores, mais lento)
FACE_THRESHOLD = 0.5  # baixo de propósito: em anonimização é melhor borrar a mais do que deixar escapar
PLATE_MODEL = "yolo-v9-s-608-license-plate-end2end"
PLATE_THRESHOLD = 0.3
PLATE_MODEL_NAME = "YOLOv9 (placas)"
TEMPORAL_SECONDS = 0.15  # cada detecção também vale para os quadros dentro desta janela
FACE_MARGIN = 0.25  # aumenta a área borrada além da caixa detectada (cabelo, orelhas)
PLATE_MARGIN = 0.15

APPLY_STEP = "Aplicando efeito"

# (x1, y1, x2, y2, tipo) — tipo "face" vira elipse, "plate" vira retângulo
Box = tuple[int, int, int, int, str]


def run(input_path: Path, output: Path | None = None, targets: str = "all", style: str = "blur",
        reporter: Reporter | None = None) -> Path:
    if targets not in TARGETS:
        raise ValueError(f"Alvo inválido: {targets}. Use um de: {', '.join(TARGETS)}")
    if style not in STYLES:
        raise ValueError(f"Estilo inválido: {style}. Use um de: {', '.join(STYLES)}")
    output = output or default_output(input_path, "blur")
    reporter = reporter or PlainReporter()
    info = probe(input_path)
    faces, plates = targets in ("all", "faces"), targets in ("all", "plates")
    detect_step = "Detectando " + " e ".join(n for n, on in (("rostos", faces), ("placas", plates)) if on)

    reporter.header(f"blur ({targets}, {style}) · {input_path.name}", info.describe())
    reporter.plan([detect_step, APPLY_STEP])
    detections = _detect(input_path, info, faces, plates, reporter, detect_step)
    window = max(1, round(TEMPORAL_SECONDS * info.fps))

    on_start = lambda cmd: reporter.command(shell_command(cmd))  # noqa: E731
    with (reporter.step(APPLY_STEP, len(detections)) as step,
          FrameWriter(output, info.width, info.height, info.fps, audio_from=input_path, on_start=on_start) as writer):
        for i, frame in enumerate(frames(input_path)):
            nearby = [b for boxes in detections[max(0, i - window) : i + window + 1] for b in boxes]
            result = anonymize(frame, nearby, style)
            writer.write(result)
            step.update(i + 1, preview=lambda: result)
    return output


def _detect(input_path: Path, info: VideoInfo, faces: bool, plates: bool, reporter: Reporter,
            step_name: str) -> list[list[Box]]:
    face_detector = plate_detector = None
    if plates:
        plate_detector = _plate_detector()

    detections: list[list[Box]] = []
    with_face = with_plate = 0
    with reporter.step(step_name, round(info.duration * info.fps)) as step:
        reporter.command(decoding(input_path, info))
        for i, frame in enumerate(frames(input_path)):
            h, w = frame.shape[:2]
            boxes: list[Box] = []
            if faces:
                scale = min(1.0, FACE_DETECT_WIDTH / w)
                size = (round(w * scale), round(h * scale))
                if face_detector is None:
                    face_detector = cv2.FaceDetectorYN.create(str(models.yunet()), "", size, FACE_THRESHOLD)
                small = frame if scale == 1.0 else cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
                with reporter.inference(FACE_MODEL):
                    _, found = face_detector.detect(small)
                for f in [] if found is None else found:
                    x, y, bw, bh = f[:4] / scale
                    boxes.append(_expand(x, y, x + bw, y + bh, FACE_MARGIN, w, h, "face"))
            if plate_detector is not None:
                with reporter.inference(PLATE_MODEL_NAME):
                    plates_found = plate_detector.predict(frame)
                for det in plates_found:
                    bb = det.bounding_box
                    boxes.append(_expand(bb.x1, bb.y1, bb.x2, bb.y2, PLATE_MARGIN, w, h, "plate"))
            detections.append(boxes)

            stats = {}
            if faces:
                with_face += any(b[4] == "face" for b in boxes)
                stats["quadros com rosto"] = with_face
            if plates:
                with_plate += any(b[4] == "plate" for b in boxes)
                stats["quadros com placa"] = with_plate
            step.update(i + 1, stats=stats, preview=lambda: draw_boxes(
                frame, [(x1, y1, x2, y2, GREEN if kind == "face" else YELLOW) for x1, y1, x2, y2, kind in boxes]))
    return detections


def _plate_detector():
    import onnxruntime as ort  # import tardio: só carrega o ONNX Runtime se for usar
    from open_image_models import create_detector

    ort.set_default_logger_severity(3)
    # o CoreML falha em quadros sem placas e a biblioteca registra isso como aviso, retornando "nenhuma placa"
    logging.getLogger("open_image_models.detection.core.yolo_v9.inference").setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # CoreML (chip Apple) é ~6x mais rápido que só CPU
        options = None
        if system.THREADS is not None:
            options = ort.SessionOptions()
            options.intra_op_num_threads = system.THREADS
        return create_detector(PLATE_MODEL, conf_thresh=PLATE_THRESHOLD, sess_options=options,
                               providers=["CoreMLExecutionProvider", "CPUExecutionProvider"])


def _expand(x1, y1, x2, y2, margin: float, w: int, h: int, kind: str) -> Box:
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return (
        max(0, int(x1 - mx)), max(0, int(y1 - my)),
        min(w, int(x2 + mx)), min(h, int(y2 + my)),
        kind,
    )


def anonymize(frame: np.ndarray, boxes: list[Box], style: str) -> np.ndarray:
    """Aplica o efeito nas áreas indicadas (elipse para rostos, retângulo para placas)."""
    if not boxes:
        return frame
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for x1, y1, x2, y2, kind in boxes:
        if x2 <= x1 or y2 <= y1:
            continue
        if kind == "face":
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
            cv2.ellipse(mask, center, ((x2 - x1) // 2, (y2 - y1) // 2), 0, 0, 360, 255, -1)
        else:
            cv2.rectangle(mask, (x1, y1), (x2 - 1, y2 - 1), 255, -1)

    x, y, rw, rh = cv2.boundingRect(mask)
    if rw == 0 or rh == 0:
        return frame
    roi = frame[y : y + rh, x : x + rw]
    effect = _effect(roi, style, block=max(8, frame.shape[0] // 60))
    out = frame.copy()
    region_mask = mask[y : y + rh, x : x + rw, None] > 0
    out[y : y + rh, x : x + rw] = np.where(region_mask, effect, roi)
    return out


def _effect(roi: np.ndarray, style: str, block: int) -> np.ndarray:
    if style == "black":
        return np.zeros_like(roi)
    h, w = roi.shape[:2]
    small = cv2.resize(roi, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    if style == "pixel":
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    # blur: reduzir a resolução antes garante que o rosto/placa não pode ser recuperado
    return cv2.GaussianBlur(cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), block)
