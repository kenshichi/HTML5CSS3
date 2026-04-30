from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple


def _safe_out_path(output_video_path: str) -> Path:
    p = Path(output_video_path)
    if not p.exists():
        return p
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")


def _ass_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_subtitled_video(input_video_path: str, ass_subtitle_path: str, output_video_path: str, subtitle_strategy: str, cover_settings: Dict) -> Tuple[str, Dict]:
    out_path = _safe_out_path(output_video_path)

    if subtitle_strategy == "Chỉ tạo file phụ đề rời":
        return "", {"skipped": True, "reason": "subtitle_only"}

    ass_filter = f"ass='{_ass_filter_path(ass_subtitle_path)}'"
    vf = ass_filter

    if subtitle_strategy == "Che phụ đề gốc và thay bằng phụ đề Việt":
        color = cover_settings.get("cover_color", "yellow")
        opacity = float(cover_settings.get("opacity", 0.75))
        height_pct = float(cover_settings.get("height_pct", 0.14))
        y_pct = float(cover_settings.get("y_pct", 0.78))
        padding = int(cover_settings.get("padding", 8))
        box_h = f"ih*{height_pct:.4f}"
        box_y = f"ih*{y_pct:.4f}-{padding}"
        draw = f"drawbox=x=0:y={box_y}:w=iw:h={box_h}:color={color}@{opacity}:t=fill"
        vf = f"{draw},{ass_filter}"

    cmd = [
        "ffmpeg", "-y", "-i", input_video_path,
        "-vf", vf,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1000:])

    settings = {
        "input_video_path": input_video_path,
        "ass_subtitle_path": ass_subtitle_path,
        "output_video_path": str(out_path),
        "subtitle_strategy": subtitle_strategy,
        "cover_settings": cover_settings,
        "ffmpeg_command": cmd,
    }
    return str(out_path), settings


def save_render_settings(output_dir: str, settings: Dict) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fp = out / "render_settings.json"
    fp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)
