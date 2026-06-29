"""Extract key frames from each clip in clips/ for visual classification.

Writes 3 JPEGs per clip to frames/<clip_stem>/: 01_start.jpg, 02_mid.jpg, 03_end.jpg.
Also writes a manifest.json summarising each clip's metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent


def extract(clip_path: Path, frames_dir: Path) -> dict:
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return {"clip": clip_path.name, "error": "could not open"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total / fps if fps else 0.0

    # Pick frames at ~15%, 50%, 85% through the clip.
    targets = {
        "01_start.jpg": int(total * 0.15),
        "02_mid.jpg": int(total * 0.50),
        "03_end.jpg": int(total * 0.85),
    }

    out_dir = frames_dir / clip_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for name, frame_idx in targets.items():
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        # Downscale long edge to ~640 to keep files small for upload/inspection.
        h, w = frame.shape[:2]
        scale = 640 / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        out_path = out_dir / name
        cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        saved.append(name)

    cap.release()
    return {
        "clip": clip_path.name,
        "stem": clip_path.stem,
        "fps": round(fps, 2),
        "frames_total": total,
        "duration_s": round(duration, 2),
        "resolution": f"{width}x{height}",
        "frames_saved": saved,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract three small JPEG frames from each MP4 clip.")
    parser.add_argument("--clips-dir", type=Path, default=ROOT / "clips", help="Folder containing MP4 clips.")
    parser.add_argument("--frames-dir", type=Path, default=ROOT / "frames", help="Folder to write extracted JPEGs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.frames_dir.mkdir(parents=True, exist_ok=True)
    clips = sorted(args.clips_dir.glob("*.mp4"))
    records = [extract(c, args.frames_dir) for c in clips]
    manifest = args.frames_dir / "manifest.json"
    manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Processed {len(records)} clips. Manifest at {manifest}")
    for r in records:
        if "error" in r:
            print(f"  [ERR] {r['clip']}: {r['error']}")
        else:
            print(f"  {r['stem']}: {r['duration_s']}s @ {r['resolution']} -> {len(r['frames_saved'])} frames")


if __name__ == "__main__":
    main()
