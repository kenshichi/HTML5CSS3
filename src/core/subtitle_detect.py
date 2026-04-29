from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List


def detect_burned_subtitle(video_path: str, output_dir: str) -> Dict:
    out = Path(output_dir) / "temp" / "subtitle_preview"
    out.mkdir(parents=True, exist_ok=True)

    # sample 3 frames
    frames: List[str] = []
    for i, ts in enumerate(["00:00:05", "00:00:15", "00:00:30"]):
        fp = out / f"frame_{i}.jpg"
        cmd = ["ffmpeg", "-y", "-ss", ts, "-i", video_path, "-vframes", "1", str(fp)]
        subprocess.run(cmd, check=False, capture_output=True, text=True)
        frames.append(str(fp))

    # heuristic: if extracted frames exist assume probable subtitle, default bottom
    exists = sum(1 for f in frames if Path(f).exists())
    has_sub = exists >= 2
    likely_position = "bottom" if has_sub else "none"
    return {
        "has_subtitle": has_sub,
        "likely_position": likely_position,
        "sample_frames": frames,
        "region": "bottom-20%" if has_sub else "none",
    }


def suggest_vietnamese_placement(has_subtitle: bool, likely_position: str) -> str:
    if not has_subtitle:
        return "bottom"
    if likely_position == "bottom":
        return "top"
    if likely_position == "top":
        return "bottom"
    return "bottom"
