"""
Herd Mapper — Pass 1 Pipeline Runner (watch-folder mode)

Watches data/incoming/{mission_id}/ for new images as the drone downloads
them via AirLink or manual USB copy.  Processes images through:
    blob_detector  (single-image thermal blob detection)
    visual_detector (batch visual obstacle inference)
    outer_guard     (airspace tiling + hazard map update)

Status is written to data/missions/{mission_id}/status.json so the FastAPI
server can poll it and push progress to the companion app.

Usage:
    python core/pipeline_runner.py --mission MISSION_ID [--model models/obstacles.onnx]
"""

import argparse
import datetime
import json
import logging
import shutil
import sys
import time
from pathlib import Path

# Watchdog is the filesystem event library (added to requirements.txt)
try:
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print(
        "pipeline_runner: watchdog not installed. "
        "Run: pip install watchdog>=4.0"
    )

# ── Project-local imports ────────────────────────────────────────────────────
# These are resolved relative to the project root.  The runner is always
# invoked from D:\Projects\herd-mapper\.
import os
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.visual_detector import detect_from_folder
from core.outer_guard import tile_airspace, haversine

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)s  %(message)s')
logger = logging.getLogger('pipeline_runner')

# Thermal blob detection (core/blob_detector.py).  If this import fails
# (e.g. sentinel-core or OpenCV missing) the pipeline CANNOT produce deer
# clusters — that must be LOUD, never silent: we log an error here, set an
# error flag in status.json, and print an error banner at finalize.
try:
    from core.blob_detector import detect_blobs_geo, cluster_detections, CLUSTER_RADIUS_M
    BLOB_DETECTOR_AVAILABLE = True
    BLOB_IMPORT_ERROR: str | None = None
except Exception as _blob_exc:  # ImportError or transitive dependency failure
    BLOB_DETECTOR_AVAILABLE = False
    BLOB_IMPORT_ERROR = f'blob_detector import failed: {_blob_exc!r}'
    logger.error(
        "PIPELINE DEGRADED — %s. Thermal blob detection WILL NOT RUN; "
        "no deer clusters will be produced. Fix the import before flying.",
        BLOB_IMPORT_ERROR,
    )

# ── Constants ────────────────────────────────────────────────────────────────
IDLE_TIMEOUT_S    = 30   # declare pass complete after N seconds of no new images
BATCH_EVERY_N     = 5    # run visual + outer_guard every N new images
IMAGE_EXTS        = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}


# ── Status helpers ───────────────────────────────────────────────────────────

def _write_json_atomic(path: Path, payload) -> None:
    """Write JSON via temp file + atomic rename (crash-safe)."""
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    tmp.replace(path)  # atomic rename


def _write_status(
    status_path: Path, status: str, processed: int, total: int,
    error: str | None = None,
) -> None:
    payload = {
        'status':       status,
        'processed':    processed,
        'total':        total,
        'error':        error,
        'last_updated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _write_json_atomic(status_path, payload)


def _write_detections(mission_dir: Path, mission_id: str, blobs: list[dict], clusters: list[dict]) -> None:
    """Persist detections.json in the schema api/server.py consumes.

    MUST match blob_detector.run / mock_data.generate_detections:
    a dict with a 'clusters' key — NOT a raw blob list (server.py reads
    detections['clusters'] and derive_waypoints needs id/lat/lon/count/
    confidence per cluster).
    """
    payload = {
        'mission_id':  mission_id,
        'total_blobs': len(blobs),
        'clusters':    clusters,
    }
    _write_json_atomic(mission_dir / 'detections.json', payload)


def _write_obstacles(mission_dir: Path, mission_id: str, cowans: list) -> None:
    from dataclasses import asdict
    raw = [asdict(c) if hasattr(c, '__dataclass_fields__') else c for c in cowans]
    _write_json_atomic(mission_dir / 'obstacles.json', raw)
    # Also write the legacy path api/server.py falls back to when the mission
    # has no property-level obstacles (data/obstacles/{id}_obstacles.json) so
    # pipeline output is actually reachable by the companion app.
    legacy_dir = mission_dir.parent.parent / 'obstacles'
    legacy_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(legacy_dir / f'{mission_id}_obstacles.json', raw)


# ── Core processing ──────────────────────────────────────────────────────────

class MissionProcessor:
    """
    Holds accumulated state for one mission and exposes process_batch().
    """

    def __init__(self, mission_id: str, model_path: str | None = None) -> None:
        self.mission_id  = mission_id
        self.model_path  = model_path

        self.mission_dir  = Path(f'data/missions/{mission_id}')
        self.images_dir   = self.mission_dir / 'images'
        self.status_path  = self.mission_dir / 'status.json'
        self.flight_log   = self.mission_dir / 'flight_log.csv'

        self.mission_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.processed_images: list[Path] = []
        self.blob_detections:  list[dict] = []
        self.clusters:         list[dict] = []
        self.visual_cowans:    list[dict] = []
        self.all_cowans:       list       = []
        self.error: str | None = BLOB_IMPORT_ERROR

        if not BLOB_DETECTOR_AVAILABLE:
            logger.error(
                "Mission '%s' starting WITHOUT thermal blob detection — %s",
                mission_id, BLOB_IMPORT_ERROR,
            )

        _write_status(self.status_path, 'waiting_for_images', 0, 0, error=self.error)

    def accept_image(self, src_path: Path) -> None:
        """Copy an incoming image into the mission images dir and run blob detection."""
        dest = self.images_dir / src_path.name
        if dest.exists():
            return  # already processed

        shutil.copy2(src_path, dest)
        self.processed_images.append(dest)

        # Single-image thermal blob detection (georeferenced blobs)
        if BLOB_DETECTOR_AVAILABLE:
            try:
                blobs = detect_blobs_geo(str(dest))
                if blobs:
                    self.blob_detections.extend(blobs)
            except Exception as exc:
                logger.error("blob detection failed for %s: %s", dest.name, exc)
                self.error = f'blob detection failed for {dest.name}: {exc}'

        _write_status(
            self.status_path, 'processing',
            len(self.processed_images), len(self.processed_images),
            error=self.error,
        )
        self._print_progress()

    def process_batch(self) -> None:
        """
        Run visual_detector on accumulated images, then outer_guard.
        Called every BATCH_EVERY_N images and at completion.
        """
        if not self.processed_images:
            return

        logger.info("Pipeline: running batch — %d images so far", len(self.processed_images))

        # Visual obstacle detection across images dir
        self.visual_cowans = detect_from_folder(
            str(self.images_dir),
            model_path=self.model_path,
        )

        # Outer Guard: use flight log if present, else skip (guard will warn)
        if self.flight_log.is_file():
            try:
                self.all_cowans = tile_airspace(
                    log_path=str(self.flight_log),
                    output_dir=str(self.mission_dir),
                    visual_detections=self.visual_cowans,
                )
            except Exception as exc:
                logger.warning("outer_guard tile_airspace failed: %s", exc)
                self.all_cowans = []
        else:
            logger.info(
                "No flight log at %s — skipping rangefinder tiling. "
                "Visual obstacles only.",
                self.flight_log,
            )
            self.all_cowans = []

        # Cluster raw georeferenced blobs into herd centroids — the schema
        # api/server.py and waypoint_generator consume.
        if BLOB_DETECTOR_AVAILABLE:
            self.clusters = cluster_detections(self.blob_detections, CLUSTER_RADIUS_M)

        _write_detections(self.mission_dir, self.mission_id, self.blob_detections, self.clusters)
        _write_obstacles(self.mission_dir, self.mission_id, self.all_cowans)
        self._print_progress()

    def finalize(self) -> None:
        """Mark mission as pass1_complete."""
        self.process_batch()
        _write_status(
            self.status_path, 'pass1_complete',
            len(self.processed_images), len(self.processed_images),
            error=self.error,
        )
        print(
            f"\nPipeline: PASS 1 COMPLETE — mission '{self.mission_id}'\n"
            f"  {len(self.processed_images)} images processed\n"
            f"  {len(self.blob_detections)} blob detections -> {len(self.clusters)} clusters\n"
            f"  {len(self.all_cowans)} obstacles in tiled airspace\n"
            f"  Results: {self.mission_dir}"
        )
        if self.error:
            print(
                f"\n  *** PIPELINE ERROR — RESULTS INCOMPLETE ***\n"
                f"  {self.error}\n"
                f"  Do NOT plan Pass 2 from this mission until resolved.\n"
            )

    def _print_progress(self) -> None:
        n_images    = len(self.processed_images)
        n_blobs     = len(self.blob_detections)
        n_clusters  = len(self.clusters)
        n_obstacles = len(self.all_cowans)
        print(
            f"Pipeline: {n_images} images processed, "
            f"{n_blobs} blobs ({n_clusters} clusters), "
            f"{n_obstacles} obstacles"
        )


# ── Watchdog event handler ────────────────────────────────────────────────────

class ImageArrivalHandler(FileSystemEventHandler):
    def __init__(self, processor: MissionProcessor) -> None:
        super().__init__()
        self.processor      = processor
        self.images_since_batch = 0
        self.last_event_ts  = time.monotonic()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        src = Path(event.src_path)
        if src.suffix.lower() not in IMAGE_EXTS:
            return

        self.processor.accept_image(src)
        self.images_since_batch += 1
        self.last_event_ts = time.monotonic()

        if self.images_since_batch >= BATCH_EVERY_N:
            self.processor.process_batch()
            self.images_since_batch = 0


# ── CLI entry-point ───────────────────────────────────────────────────────────

def run_pipeline(mission_id: str, model_path: str | None = None) -> None:
    watch_dir = Path(f'data/incoming/{mission_id}')
    watch_dir.mkdir(parents=True, exist_ok=True)

    processor = MissionProcessor(mission_id, model_path=model_path)

    # Process any images that already exist in the watch dir
    existing = sorted(p for p in watch_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if existing:
        logger.info("Pipeline: found %d existing images in watch dir", len(existing))
        for img in existing:
            processor.accept_image(img)
        processor.process_batch()

    if not WATCHDOG_AVAILABLE:
        # Fallback: polling loop (watchdog not installed)
        logger.warning(
            "watchdog not available — falling back to polling every 5 seconds. "
            "Install watchdog>=4.0 for efficient event-driven watching."
        )
        _polling_loop(processor, watch_dir)
        return

    handler  = ImageArrivalHandler(processor)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    print(f"Pipeline: watching {watch_dir} for mission '{mission_id}'")
    print("  Press Ctrl-C to stop.")

    try:
        idle_logged = False
        while True:
            time.sleep(1)
            idle_s = time.monotonic() - handler.last_event_ts
            if (
                idle_s >= IDLE_TIMEOUT_S
                and processor.processed_images
                and handler.images_since_batch > 0
            ):
                # Flush any remaining images that didn't hit the batch threshold
                processor.process_batch()
                handler.images_since_batch = 0

            if idle_s >= IDLE_TIMEOUT_S and processor.processed_images and not idle_logged:
                processor.finalize()
                idle_logged = True
                # Keep watching — operator may add more images manually

    except KeyboardInterrupt:
        observer.stop()
        print("\nPipeline: shutting down (KeyboardInterrupt)")
        if processor.processed_images and not idle_logged:
            processor.finalize()

    observer.join()


def _polling_loop(processor: MissionProcessor, watch_dir: Path) -> None:
    """Fallback polling loop when watchdog is unavailable."""
    seen: set[str] = set()
    last_new_ts = time.monotonic()
    images_since_batch = 0

    print(f"Pipeline (polling): watching {watch_dir} for mission '{processor.mission_id}'")
    print("  Press Ctrl-C to stop.")

    try:
        while True:
            time.sleep(5)
            current = {
                p.name: p
                for p in watch_dir.iterdir()
                if p.suffix.lower() in IMAGE_EXTS
            }
            new_files = {n: p for n, p in current.items() if n not in seen}
            for name, path in sorted(new_files.items()):
                processor.accept_image(path)
                seen.add(name)
                images_since_batch += 1
                last_new_ts = time.monotonic()

                if images_since_batch >= BATCH_EVERY_N:
                    processor.process_batch()
                    images_since_batch = 0

            idle_s = time.monotonic() - last_new_ts
            if idle_s >= IDLE_TIMEOUT_S and processor.processed_images:
                if images_since_batch > 0:
                    processor.process_batch()
                    images_since_batch = 0
                processor.finalize()
                break  # polling loop exits after completion; watchdog loop stays alive

    except KeyboardInterrupt:
        print("\nPipeline: shutting down (KeyboardInterrupt)")
        if processor.processed_images:
            processor.finalize()


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description='Herd Mapper Pass 1 Pipeline Runner — watches incoming images and runs full processing chain'
    )
    parser.add_argument(
        '--mission', required=True,
        help='Mission ID (e.g. demo, 20260423_chesapeake)'
    )
    parser.add_argument(
        '--model', default=None,
        help='Path to obstacles.onnx for visual detection (omit = mock mode, returns no visual obstacles)'
    )
    args = parser.parse_args()
    run_pipeline(args.mission, model_path=args.model)


if __name__ == '__main__':
    _cli()
