"""
Visual Obstacle Detector — ground-side ONNX inference layer for the Outer Guard.

Runs a YOLOv8 ONNX model on RGB camera images captured during Pass 1.
Returns Cowan-format obstacle dicts that can be merged with rangefinder detections
via outer_guard.merge_visual_cowans().

No companion computer required — all inference runs on the operator's laptop.
Model: 10-class obstacle detector (obstacles.onnx).

Mock mode: if model_path is None or the file is not present, the detector logs
a warning and returns [] — the rest of the pipeline is unaffected.

Usage (CLI):
    python core/visual_detector.py \\
        --images data/missions/MISSION_ID \\
        --model models/obstacles.onnx \\
        --output data/obstacles/

Usage (API):
    from core.visual_detector import detect_obstacles, detect_from_folder
    cowans = detect_from_folder('data/missions/demo/images', model_path=None)
"""

import argparse
import json
import logging
import os
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ─── 10-class obstacle taxonomy ─────────────────────────────────────────────
# These indices MUST match the class order used during training (obstacle_classes.yaml).
CLASS_NAMES: list[str] = [
    'tree',             # 0
    'building',         # 1
    'fence_line',       # 2
    'power_line',       # 3
    'tower',            # 4
    'guy_wire',         # 5
    'water',            # 6
    'vehicle',          # 7
    'antenna',          # 8
    'irrigation_pivot', # 9
]

# Type-specific exclusion radii (metres) — mirrors Outer Guard conventions.
EXCLUSION_RADII: dict[str, float] = {
    'tower':            33.0,
    'guy_wire':         20.0,
    'power_line':        8.0,
    'fence_line':        4.0,
    'building':         10.0,
    'tree':              5.0,
    'water':            15.0,
    'vehicle':          10.0,
    'antenna':          15.0,
    'irrigation_pivot': 20.0,
}

# Confidence band thresholds
CONF_HIGH   = 0.75
CONF_MEDIUM = 0.60
DEFAULT_CONF_THRESHOLD = 0.45
DEFAULT_NMS_IOU        = 0.50

# ─── Inference provenance ────────────────────────────────────────────────────
# `mode` travels with every result so a caller can never mistake "the model was
# absent and we returned nothing" for "the model ran and found nothing".
# 'stub' is the SAFE DEFAULT: any result whose provenance was not explicitly
# set to 'onnx' is treated as stub. Mirrors the fence-mapper Phase 3 contract
# in core/fence_condition_detector.py so both projects report absence alike.
VISUAL_MODE_ONNX: str = 'onnx'
VISUAL_MODE_STUB: str = 'stub'

# Surfaced wherever visual obstacles reach an operator or a written artifact.
# A missed obstacle lowers the computed Pass 2 safe altitude, so silent absence
# is a flight-safety condition, not a cosmetic gap.
VISUAL_STUB_BANNER_TEXT: str = (
    "DEGRADED RESULT: VISUAL OBSTACLE DETECTION DID NOT RUN. No obstacle "
    "model was loaded, so this obstacle set contains NO visually detected "
    "hazards (power lines, guy wires, towers, antennas). Safe-altitude and "
    "waypoint-lock values derived from it are incomplete. Do not fly Pass 2 "
    "against this result without an independent obstacle check."
)


def resolve_visual_mode(model_path: str | None) -> str:
    """Provenance mode for a model path. Safe by default: absent file = stub."""
    if model_path is None or not Path(model_path).is_file():
        return VISUAL_MODE_STUB
    return VISUAL_MODE_ONNX


def visual_is_degraded(record: dict | None) -> bool:
    """Safe-by-default provenance check for an in-flight or persisted record.

    Anything not verifiably 'onnx' is degraded — including a legacy record
    written before the mode field existed, and None.
    """
    if not record:
        return True
    mode = record.get('visual_mode', record.get('mode', VISUAL_MODE_STUB))
    return mode != VISUAL_MODE_ONNX


# Supported image extensions
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}

# Deduplication proximity: visual detections within this pixel distance (after
# projection) on the same image are considered the same object.
DEDUP_PIXEL_DIST = 40


# ─── Preprocessing ───────────────────────────────────────────────────────────

def _letterbox(image: np.ndarray, target: int = 640) -> tuple[np.ndarray, float, tuple[int, int]]:
    """
    Resize image to target x target with letterboxing (grey padding).
    Returns (letterboxed_image, scale, (pad_left, pad_top)).
    """
    h, w = image.shape[:2]
    scale = min(target / h, target / w)
    new_h, new_w = int(h * scale), int(w * scale)

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((target, target, 3), 114, dtype=np.uint8)
    pad_top  = (target - new_h) // 2
    pad_left = (target - new_w) // 2
    canvas[pad_top:pad_top + new_h, pad_left:pad_left + new_w] = resized

    return canvas, scale, (pad_left, pad_top)


def _preprocess(image_bgr: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
    """
    Letterbox, convert BGR→RGB, normalize 0-1, add batch dim.
    Returns (blob [1,3,640,640] float32, scale, pad_xy).
    """
    lb, scale, pad = _letterbox(image_bgr, 640)
    rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)
    blob = rgb.astype(np.float32) / 255.0           # HWC, 0-1
    blob = np.transpose(blob, (2, 0, 1))             # CHW
    blob = np.expand_dims(blob, 0)                   # BCHW
    return blob, scale, pad


# ─── Output parsing ──────────────────────────────────────────────────────────

def _parse_yolov8_output(
    output: np.ndarray,
    scale: float,
    pad: tuple[int, int],
    conf_thresh: float,
    iou_thresh: float,
    orig_shape: tuple[int, int],
) -> list[dict]:
    """
    Parse YOLOv8 detection output tensor.

    YOLOv8 ONNX export shape: [1, 84, 8400]
      - 84 = 4 (cx,cy,w,h) + 80 classes (COCO default).
      For our 10-class model: [1, 14, 8400] = 4 + 10.

    Returns list of dicts: {class_id, class_name, score, x1, y1, x2, y2}
    in original image pixel coordinates.
    """
    # output shape: (1, num_channels, num_anchors)
    pred = output[0]  # (num_channels, num_anchors)
    pred = pred.T     # (num_anchors, num_channels)

    num_classes = pred.shape[1] - 4
    boxes_raw  = pred[:, :4]              # cx, cy, w, h (letterbox coords)
    class_probs = pred[:, 4:4 + num_classes]

    # Class with highest probability per anchor
    class_ids = np.argmax(class_probs, axis=1)
    scores     = class_probs[np.arange(len(class_probs)), class_ids]

    # Filter by confidence threshold
    mask = scores >= conf_thresh
    if not mask.any():
        return []

    boxes_raw  = boxes_raw[mask]
    class_ids  = class_ids[mask]
    scores     = scores[mask]

    # cx,cy,w,h → x1,y1,x2,y2 (letterbox space)
    x1 = boxes_raw[:, 0] - boxes_raw[:, 2] / 2
    y1 = boxes_raw[:, 1] - boxes_raw[:, 3] / 2
    x2 = boxes_raw[:, 0] + boxes_raw[:, 2] / 2
    y2 = boxes_raw[:, 1] + boxes_raw[:, 3] / 2

    pad_left, pad_top = pad
    orig_h, orig_w = orig_shape

    # Remove letterbox padding and undo scale
    x1 = np.clip((x1 - pad_left) / scale, 0, orig_w)
    y1 = np.clip((y1 - pad_top)  / scale, 0, orig_h)
    x2 = np.clip((x2 - pad_left) / scale, 0, orig_w)
    y2 = np.clip((y2 - pad_top)  / scale, 0, orig_h)

    # NMS via OpenCV (class-agnostic then filter)
    boxes_cv = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
    scores_list = scores.tolist()

    keep_indices = cv2.dnn.NMSBoxes(
        boxes_cv, scores_list, conf_thresh, iou_thresh
    )

    detections = []
    if len(keep_indices) == 0:
        return detections

    # OpenCV NMSBoxes returns flat array in older versions, nested in newer
    if isinstance(keep_indices, np.ndarray):
        keep_indices = keep_indices.flatten()

    for idx in keep_indices:
        cid  = int(class_ids[idx])
        name = CLASS_NAMES[cid] if cid < len(CLASS_NAMES) else f'class_{cid}'
        detections.append({
            'class_id':   cid,
            'class_name': name,
            'score':      float(scores[idx]),
            'x1': float(x1[idx]),
            'y1': float(y1[idx]),
            'x2': float(x2[idx]),
            'y2': float(y2[idx]),
        })

    return detections


# ─── Cowan conversion ────────────────────────────────────────────────────────

def _confidence_band(score: float) -> str:
    if score >= CONF_HIGH:
        return 'HIGH'
    if score >= CONF_MEDIUM:
        return 'MEDIUM'
    return 'LOW'


def _bbox_to_height_estimate(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Rough heuristic: larger bounding boxes imply closer / taller objects.
    Returns a placeholder height in metres — caller should enrich from telemetry.
    Currently returns 0.0 as documented placeholder; GPS enrichment is a future pass.
    """
    return 0.0


def _detection_to_cowan(det: dict, idx: int) -> dict:
    """Convert a single raw detection dict to Cowan-format dict."""
    class_name = det['class_name']
    score      = det['score']
    return {
        'id':                 f"vis_{class_name}_{idx}",
        'lat':                None,
        'lon':                None,
        'height_m':           _bbox_to_height_estimate(det['x1'], det['y1'], det['x2'], det['y2']),
        'type':               class_name,
        'confidence':         _confidence_band(score),
        'exclusion_radius_m': EXCLUSION_RADII.get(class_name, 10.0),
        'note':               f"Visual detection — {class_name} ({score:.0%} confidence)",
        'source':             'visual',
        # Bounding box retained for downstream GPS projection (stripped before JSON export)
        '_bbox':              {'x1': det['x1'], 'y1': det['y1'], 'x2': det['x2'], 'y2': det['y2']},
        '_image_path':        det.get('image_path', ''),
    }


# ─── Deduplication ───────────────────────────────────────────────────────────

def _dedup_detections(cowans: list[dict]) -> list[dict]:
    """
    Remove near-duplicate visual detections across images.
    Two detections are duplicates if same type AND bbox centres within DEDUP_PIXEL_DIST
    on the SAME image.  Cross-image deduplication uses GPS enrichment (future pass).
    For now, only within-image dedup is applied (NMS already handles most of this).
    """
    # Group by image_path + type, apply centre-distance filter
    kept: list[dict] = []
    for cowan in cowans:
        bbox  = cowan.get('_bbox', {})
        cx    = (bbox.get('x1', 0) + bbox.get('x2', 0)) / 2
        cy    = (bbox.get('y1', 0) + bbox.get('y2', 0)) / 2
        ctype = cowan['type']
        cimg  = cowan.get('_image_path', '')

        duplicate = False
        for existing in kept:
            if existing['type'] != ctype:
                continue
            if existing.get('_image_path', '') != cimg:
                continue
            ex_bbox = existing.get('_bbox', {})
            ex_cx   = (ex_bbox.get('x1', 0) + ex_bbox.get('x2', 0)) / 2
            ex_cy   = (ex_bbox.get('y1', 0) + ex_bbox.get('y2', 0)) / 2
            dist    = ((cx - ex_cx) ** 2 + (cy - ex_cy) ** 2) ** 0.5
            if dist < DEDUP_PIXEL_DIST:
                duplicate = True
                break

        if not duplicate:
            kept.append(cowan)

    return kept


# ─── Public API ──────────────────────────────────────────────────────────────

def detect_obstacles(
    image_path: str,
    model_path: str | None = None,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    iou_threshold: float = DEFAULT_NMS_IOU,
) -> list[dict]:
    """
    Run ONNX obstacle detection on a single RGB image.

    Parameters
    ----------
    image_path : str
        Path to an RGB image (JPG, PNG, TIFF, …).
    model_path : str | None
        Path to obstacles.onnx.  If None or file not found, returns [] (mock mode).
    conf_threshold : float
        Minimum detection confidence (default 0.45).
    iou_threshold : float
        NMS IoU threshold (default 0.50).

    Returns
    -------
    list[dict]
        Cowan-format dicts.  lat/lon are None — enrich with GPS before merging.
    """
    # ── Mock mode guard ──────────────────────────────────────────────────────
    if model_path is None or not Path(model_path).is_file():
        effective_path = model_path or '<none>'
        print(f"visual_detector: no model at {effective_path} — skipping visual scan")
        return []

    # ── Load image ───────────────────────────────────────────────────────────
    img_path = Path(image_path)
    if not img_path.is_file():
        logger.warning("visual_detector: image not found: %s", image_path)
        return []

    image_bgr = cv2.imread(str(img_path))
    if image_bgr is None:
        logger.warning("visual_detector: could not decode image: %s", image_path)
        return []

    orig_h, orig_w = image_bgr.shape[:2]

    # ── Preprocess ───────────────────────────────────────────────────────────
    blob, scale, pad = _preprocess(image_bgr)

    # ── ONNX inference ───────────────────────────────────────────────────────
    try:
        import onnxruntime as ort  # lazy import — not required if mock mode
    except ImportError:
        logger.error(
            "visual_detector: onnxruntime not installed. "
            "Run: pip install onnxruntime>=1.18"
        )
        return []

    try:
        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 3  # suppress ONNX Runtime info spam

        # Prefer CUDA (RTX 5060 Ti) → fall back to CPU
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        session   = ort.InferenceSession(str(model_path), sess_opts=sess_opts, providers=providers)

        input_name  = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        raw_output  = session.run([output_name], {input_name: blob})
    except Exception as exc:
        logger.error("visual_detector: ONNX inference failed: %s", exc)
        return []

    # ── Parse detections ─────────────────────────────────────────────────────
    raw_dets = _parse_yolov8_output(
        raw_output[0],
        scale=scale,
        pad=pad,
        conf_thresh=conf_threshold,
        iou_thresh=iou_threshold,
        orig_shape=(orig_h, orig_w),
    )

    # Tag each detection with its source image for deduplication
    for det in raw_dets:
        det['image_path'] = str(img_path)

    # ── Convert to Cowan format ───────────────────────────────────────────────
    cowans = [_detection_to_cowan(det, idx) for idx, det in enumerate(raw_dets)]

    logger.info(
        "visual_detector: %s — %d detection(s): %s",
        img_path.name,
        len(cowans),
        ', '.join(c['type'] for c in cowans),
    )

    return cowans


def detect_from_folder(
    image_dir: str,
    model_path: str | None = None,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    iou_threshold: float = DEFAULT_NMS_IOU,
) -> list[dict]:
    """
    Run detect_obstacles on every image in image_dir.
    Deduplicates within-image near-duplicate bounding boxes.

    Parameters
    ----------
    image_dir : str
        Directory containing RGB images from Pass 1.
    model_path : str | None
        Path to obstacles.onnx.  None → mock mode (returns []).
    conf_threshold, iou_threshold : float
        Forwarded to detect_obstacles.

    Returns
    -------
    list[dict]
        Deduplicated Cowan-format dicts across all images.
    """
    dir_path = Path(image_dir)
    if not dir_path.is_dir():
        logger.warning("visual_detector: image directory not found: %s", image_dir)
        return []

    image_files = sorted(
        p for p in dir_path.iterdir()
        if p.suffix.lower() in IMAGE_EXTS
    )

    if not image_files:
        logger.info("visual_detector: no images found in %s", image_dir)
        return []

    all_cowans: list[dict] = []
    for img_path in image_files:
        detections = detect_obstacles(
            str(img_path),
            model_path=model_path,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )
        all_cowans.extend(detections)

        # In mock mode detect_obstacles returns [] immediately; no need to iterate further
        if model_path is None or not Path(model_path).is_file():
            break

    deduped = _dedup_detections(all_cowans)

    print(
        f"visual_detector: scanned {len(image_files)} image(s) — "
        f"{len(all_cowans)} raw detections, {len(deduped)} after dedup"
    )

    return deduped


def detect_from_folder_with_provenance(
    image_dir: str,
    model_path: str | None = None,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    iou_threshold: float = DEFAULT_NMS_IOU,
) -> dict:
    """Run the folder scan and stamp inference provenance onto the result.

    PRIMARY entry point. Prefer this over detect_from_folder(), which returns a
    bare list and therefore cannot distinguish "no model" from "no obstacles".

    Returns
    -------
    dict
        {'mode': 'onnx'|'stub', 'model_path': str|None, 'obstacles': list[dict]}
    """
    mode = resolve_visual_mode(model_path)
    obstacles = detect_from_folder(
        image_dir,
        model_path=model_path,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
    )
    if mode == VISUAL_MODE_STUB:
        print()
        print(f"  *** {VISUAL_STUB_BANNER_TEXT} ***")
        print()
    return {
        'mode':       mode,
        'model_path': str(model_path) if mode == VISUAL_MODE_ONNX else None,
        'obstacles':  obstacles,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description='Visual Obstacle Detector — runs YOLOv8 ONNX inference on Pass 1 RGB images'
    )
    parser.add_argument(
        '--images', required=True,
        help='Directory of RGB images from the mission (e.g. data/missions/MISSION_ID)'
    )
    parser.add_argument(
        '--model', default=None,
        help='Path to obstacles.onnx (omit or absent file = mock mode)'
    )
    parser.add_argument(
        '--output', default='data/obstacles/',
        help='Directory to write detections JSON (default: data/obstacles/)'
    )
    parser.add_argument(
        '--conf', type=float, default=DEFAULT_CONF_THRESHOLD,
        help=f'Confidence threshold (default: {DEFAULT_CONF_THRESHOLD})'
    )
    parser.add_argument(
        '--iou', type=float, default=DEFAULT_NMS_IOU,
        help=f'NMS IoU threshold (default: {DEFAULT_NMS_IOU})'
    )
    args = parser.parse_args()

    # Resolve mission ID from images path
    mission_id = Path(args.images).stem

    visual = detect_from_folder_with_provenance(
        args.images,
        model_path=args.model,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
    )
    cowans = visual['obstacles']

    # Strip internal-only fields before persisting
    exportable = [
        {k: v for k, v in c.items() if not k.startswith('_')}
        for c in cowans
    ]

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f'{mission_id}_visual_obstacles.json'

    payload = {
        'mission_id':      mission_id,
        'visual_mode':     visual['mode'],
        'visual_degraded': visual['mode'] != VISUAL_MODE_ONNX,
        'obstacles':       exportable,
    }
    with open(out_file, 'w') as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Saved {len(exportable)} visual obstacle(s) to {out_file}")
    if visual['mode'] != VISUAL_MODE_ONNX:
        print(f"  *** {VISUAL_STUB_BANNER_TEXT} ***")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s  %(message)s')
    _cli()
