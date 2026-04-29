from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image


def _video_duration(video_path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], text=True).strip()
    return max(1.0, float(out))


def _extract_frame(video_path: str, ts_sec: float, out_path: Path) -> bool:
    cmd = ["ffmpeg", "-y", "-ss", f"{ts_sec:.3f}", "-i", video_path, "-frames:v", "1", "-q:v", "2", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and out_path.exists()


def _region_score(img: np.ndarray) -> float:
    if img.size == 0:
        return 0.0
    rgb = img[..., :3].astype(np.float32)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    bright = (luma > 180).mean()
    yellow = ((rgb[..., 0] > 170) & (rgb[..., 1] > 150) & (rgb[..., 2] < 140)).mean()
    gx = np.abs(np.diff(luma, axis=1)).mean() / 255.0
    gy = np.abs(np.diff(luma, axis=0)).mean() / 255.0
    horizontal_band = max(0.0, gx - gy)
    return float(0.45 * bright + 0.25 * yellow + 0.30 * horizontal_band)


def detect_source_subtitles(video_path: str, output_dir: str) -> Dict:
    out_dir = Path(output_dir)
    frame_dir = out_dir / "subtitle_detection_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    duration = _video_duration(video_path)
    sample_points = [0.10, 0.25, 0.50, 0.75, 0.90]

    top_scores: List[float] = []
    bot_scores: List[float] = []
    frames: List[str] = []

    for i, ratio in enumerate(sample_points):
        ts = duration * ratio
        fp = frame_dir / f"sample_{i+1}_{int(ratio*100)}.jpg"
        if not _extract_frame(video_path, ts, fp):
            continue
        frames.append(str(fp))
        arr = np.array(Image.open(fp).convert("RGB"))
        h = arr.shape[0]
        top = arr[: int(h * 0.25), :, :]
        bottom = arr[int(h * 0.70):, :, :]
        top_scores.append(_region_score(top))
        bot_scores.append(_region_score(bottom))

    if not frames:
        result = {
            "has_source_subtitle": "unknown",
            "probable_position": "unknown",
            "confidence": 0.0,
            "suggested_strategy": "Chỉ tạo file phụ đề rời",
            "sample_frames": [],
        }
    else:
        top_avg = float(np.mean(top_scores)) if top_scores else 0.0
        bot_avg = float(np.mean(bot_scores)) if bot_scores else 0.0
        diff = abs(bot_avg - top_avg)
        confidence = min(1.0, max(top_avg, bot_avg) * 2.2 + diff)
        has = max(top_avg, bot_avg) > 0.11
        pos = "bottom" if bot_avg > top_avg else "top"
        if not has:
            suggestion = "Thêm phụ đề Việt ở dưới"
            pos = "unknown"
        elif confidence < 0.45:
            suggestion = "Không chắc chắn, vui lòng kiểm tra thủ công"
        elif pos == "bottom":
            suggestion = "Thêm phụ đề Việt ở trên"
        else:
            suggestion = "Thêm phụ đề Việt ở dưới"
        result = {
            "has_source_subtitle": bool(has),
            "probable_position": pos,
            "confidence": round(confidence, 3),
            "suggested_strategy": suggestion,
            "sample_frames": frames,
        }

    (out_dir / "subtitle_detection.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
