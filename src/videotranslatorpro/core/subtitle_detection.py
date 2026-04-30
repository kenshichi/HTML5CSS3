from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image


def _extract_frame(video_path: str, ts_sec: float, out_path: Path) -> bool:
    r = subprocess.run(["ffmpeg", "-y", "-ss", f"{ts_sec:.3f}", "-i", video_path, "-frames:v", "1", "-q:v", "2", str(out_path)], capture_output=True, text=True)
    return r.returncode == 0 and out_path.exists()


def _region_score(img: np.ndarray) -> float:
    if img.size == 0:
        return 0.0
    rgb = img[..., :3].astype(np.float32)
    y = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    bright = (y > 180).mean()
    yellow = ((rgb[..., 0] > 170) & (rgb[..., 1] > 150) & (rgb[..., 2] < 140)).mean()
    edge_x = np.abs(np.diff(y, axis=1)).mean() / 255.0
    edge_y = np.abs(np.diff(y, axis=0)).mean() / 255.0
    band = max(0.0, edge_x - edge_y)
    return float(0.4 * bright + 0.25 * yellow + 0.35 * band)


def detect_burned_in_subtitles(input_video_path: str, video_duration: float, output_dir: str) -> dict:
    out_dir = Path(output_dir)
    frame_dir = out_dir / "subtitle_detection_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    sample_ratios = [0.10, 0.25, 0.50, 0.75, 0.90]
    timestamps = [video_duration * r for r in sample_ratios]

    top_scores: List[float] = []
    bot_scores: List[float] = []
    frames: List[str] = []
    notes: List[str] = []

    for i, ts in enumerate(timestamps, start=1):
        fp = frame_dir / f"frame_{i:03d}.jpg"
        if not _extract_frame(input_video_path, ts, fp):
            continue
        frames.append(str(fp))
        arr = np.array(Image.open(fp).convert("RGB"))
        h = arr.shape[0]
        top_scores.append(_region_score(arr[: int(h * 0.25), :, :]))
        bot_scores.append(_region_score(arr[int(h * 0.70):, :, :]))

    has, pos, conf, strategy = "unknown", "unknown", 0.0, "Thêm phụ đề Việt ở dưới"
    if frames:
        t = float(np.mean(top_scores)) if top_scores else 0.0
        b = float(np.mean(bot_scores)) if bot_scores else 0.0
        diff = abs(b - t)
        conf = round(min(1.0, max(t, b) * 2.0 + diff), 3)
        if max(t, b) < 0.10:
            has = False
            notes.append("Không phát hiện phụ đề gốc rõ ràng.")
        elif conf < 0.45:
            has = "unknown"
            notes.append("Không chắc chắn có phụ đề gốc hay không. Vui lòng kiểm tra preview.")
        else:
            has = True
            if b > t:
                pos = "bottom"
                strategy = "Đặt phụ đề Việt trên phụ đề gốc"
            else:
                pos = "top"
                strategy = "Đặt phụ đề Việt dưới phụ đề gốc"

    result = {
        "has_source_subtitle": has,
        "probable_position": pos,
        "confidence": conf,
        "suggested_strategy": strategy,
        "sample_frames": frames,
        "sample_timestamps": timestamps,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    (out_dir / "subtitle_detection.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
