"""
YOLOv8 Obstacle Model Training Launcher

Fine-tunes a YOLOv8n (nano) model on the 10-class obstacle dataset defined in
data/obstacle_classes.yaml and exports to models/obstacles.onnx automatically.

Hardware target: operator laptop with RTX 5060 Ti (16 GB VRAM).
Expected training time: 2-6 hours for 100 epochs at 640px with yolov8n.

Prerequisite:
    pip install ultralytics>=8.2

Dataset setup:
    See data/obstacle_classes.yaml for dataset layout and Roboflow download notes.
    Minimum recommended images per class: 200 for common classes (tree, building,
    vehicle, water), 50+ for rare classes (guy_wire, irrigation_pivot).

Usage:
    python scripts/train_obstacles.py
    python scripts/train_obstacles.py --weights yolov8s.pt   # small model
    python scripts/train_obstacles.py --epochs 200 --batch 8
    python scripts/train_obstacles.py --help
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure project root is importable even when invoked from a different cwd
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def train(
    weights: str = 'yolov8n.pt',
    data_yaml: str | None = None,
    epochs: int = 100,
    batch: int = 16,
    imgsz: int = 640,
    patience: int = 15,
    device: int | str = 0,
    project: str = 'runs/obstacle_train',
    name: str = 'exp',
    export_path: str = 'models/obstacles.onnx',
) -> None:
    """
    Run YOLOv8 training and auto-export to ONNX.

    Parameters
    ----------
    weights : str
        Starting weights.  Use 'yolov8n.pt' (nano, fastest) for initial runs.
        'yolov8s.pt' / 'yolov8m.pt' for production accuracy.
    data_yaml : str | None
        Path to dataset YAML.  Defaults to data/obstacle_classes.yaml.
    epochs : int
        Maximum training epochs (early stopping via patience).
    batch : int
        Batch size.  16 fits comfortably on RTX 5060 Ti at 640px.
    imgsz : int
        Training image size.  640 is YOLOv8 standard.
    patience : int
        Early stopping patience (epochs without improvement).
    device : int | str
        GPU device index (0 for first GPU) or 'cpu'.
    project : str
        Output directory for training runs.
    name : str
        Experiment sub-directory name.
    export_path : str
        Destination path for the exported ONNX model.
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "ERROR: ultralytics is not installed.\n"
            "Run: pip install ultralytics>=8.2"
        )
        sys.exit(1)

    if data_yaml is None:
        data_yaml = str(PROJECT_ROOT / 'data' / 'obstacle_classes.yaml')

    data_path = Path(data_yaml)
    if not data_path.is_file():
        print(f"ERROR: Dataset YAML not found at {data_path}")
        print("       See data/obstacle_classes.yaml for dataset setup instructions.")
        sys.exit(1)

    print("=" * 60)
    print("Herd Mapper — Obstacle Model Training")
    print("=" * 60)
    print(f"  Weights  : {weights}")
    print(f"  Dataset  : {data_path}")
    print(f"  Epochs   : {epochs}  (patience={patience})")
    print(f"  Batch    : {batch}")
    print(f"  Image sz : {imgsz}")
    print(f"  Device   : {device}")
    print(f"  Export   : {export_path}")
    print()

    # ── Load base model ───────────────────────────────────────────────────────
    model = YOLO(weights)

    # ── Train ─────────────────────────────────────────────────────────────────
    results = model.train(
        data=str(data_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        patience=patience,
        device=device,
        project=project,
        name=name,
        # Augmentation settings — conservative for aerial imagery
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        degrees=90.0,       # aerial images can be rotated freely
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        # Logging
        verbose=True,
        plots=True,
    )

    best_weights = Path(project) / name / 'weights' / 'best.pt'
    if not best_weights.is_file():
        # Ultralytics sometimes uses a different path structure
        best_weights = Path(results.save_dir) / 'weights' / 'best.pt'  # type: ignore[union-attr]

    print(f"\nTraining complete.  Best weights: {best_weights}")

    # ── Export to ONNX ────────────────────────────────────────────────────────
    print(f"\nExporting to ONNX (opset=12, simplified)...")
    best_model = YOLO(str(best_weights))
    best_model.export(
        format='onnx',
        opset=12,
        simplify=True,
        imgsz=imgsz,
        half=False,         # FP32 for maximum onnxruntime compatibility
    )

    # Ultralytics exports next to the .pt file; move it to models/
    exported_onnx = best_weights.with_suffix('.onnx')
    if not exported_onnx.is_file():
        print(f"WARNING: expected ONNX at {exported_onnx} — check ultralytics export output above")
        return

    dest = Path(export_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    exported_onnx.rename(dest)

    print(f"\nModel saved to: {dest}")
    print("\nNext step:")
    print(f"  python core/visual_detector.py --images data/missions/demo --model {dest}")


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description='Train YOLOv8 10-class obstacle detector and export to ONNX'
    )
    parser.add_argument(
        '--weights', default='yolov8n.pt',
        help='Base YOLOv8 weights to fine-tune from (default: yolov8n.pt). '
             'Options: yolov8n.pt (nano), yolov8s.pt (small), yolov8m.pt (medium).'
    )
    parser.add_argument(
        '--data', default=None,
        help='Path to dataset YAML (default: data/obstacle_classes.yaml)'
    )
    parser.add_argument(
        '--epochs', type=int, default=100,
        help='Maximum training epochs (default: 100)'
    )
    parser.add_argument(
        '--batch', type=int, default=16,
        help='Batch size — reduce to 8 if VRAM is tight (default: 16)'
    )
    parser.add_argument(
        '--imgsz', type=int, default=640,
        help='Training image size (default: 640)'
    )
    parser.add_argument(
        '--patience', type=int, default=15,
        help='Early stopping patience in epochs (default: 15)'
    )
    parser.add_argument(
        '--device', default='0',
        help='GPU device index or "cpu" (default: 0 = first GPU)'
    )
    parser.add_argument(
        '--export', default='models/obstacles.onnx',
        help='Output ONNX path (default: models/obstacles.onnx)'
    )
    parser.add_argument(
        '--project', default='runs/obstacle_train',
        help='Training runs directory (default: runs/obstacle_train)'
    )
    parser.add_argument(
        '--name', default='exp',
        help='Experiment name sub-directory (default: exp)'
    )

    args = parser.parse_args()

    # Convert device: int if numeric
    device: int | str = int(args.device) if args.device.isdigit() else args.device

    train(
        weights=args.weights,
        data_yaml=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        device=device,
        project=args.project,
        name=args.name,
        export_path=args.export,
    )


if __name__ == '__main__':
    _cli()
