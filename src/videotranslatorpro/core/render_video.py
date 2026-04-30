from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict


def _safe_out_path(output_video_path: str) -> Path:
    p = Path(output_video_path)
    if not p.exists():
        return p
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")


def _ass_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_subtitled_video(input_video_path: str, ass_subtitle_path: str, output_video_path: str, subtitle_strategy: str, cover_settings: dict, video_metadata: dict | None = None) -> dict:
    out_path = _safe_out_path(output_video_path)
    strategy = subtitle_strategy
    pos = (video_metadata or {}).get("source_subtitle_position", "unknown")
    suggested = (video_metadata or {}).get("subtitle_strategy_suggested", "Thêm phụ đề Việt ở dưới")

    if strategy == "Tự động, khuyên dùng":
        strategy = suggested or "Thêm phụ đề Việt ở dưới"

    if strategy == "Chỉ tạo file phụ đề rời":
        return {"success": True, "output_path": "", "ffmpeg_command": "", "error": "", "skipped": True}

    vf = f"ass='{_ass_filter_path(ass_subtitle_path)}'"
    if strategy == "Che phụ đề gốc và thay bằng phụ đề Việt":
        color = cover_settings.get("cover_color", "yellow")
        opacity = float(cover_settings.get("opacity", 1.0))
        height_pct = float(cover_settings.get("height_pct", 0.18))
        if pos == "top":
            y_pct = 0.05
        elif pos == "bottom":
            y_pct = 0.78
        else:
            y_pct = float(cover_settings.get("y_pct", 0.78))
        padding = int(cover_settings.get("padding", 8))
        draw = f"drawbox=x=0:y=ih*{y_pct:.3f}-{padding}:w=iw:h=ih*{height_pct:.3f}:color={color}@{opacity}:t=fill"
        vf = f"{draw},{vf}"

    cmd = [
        "ffmpeg", "-y", "-i", input_video_path,
        "-vf", vf,
        "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"success": False, "output_path": "", "ffmpeg_command": " ".join(cmd), "error": r.stderr[-1200:]}
    return {"success": True, "output_path": str(out_path), "ffmpeg_command": " ".join(cmd), "error": "", "strategy_used": strategy}


def save_render_settings(output_dir: str, settings: Dict) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(settings)
    payload["created_at"] = datetime.utcnow().isoformat() + "Z"
    fp = out / "render_settings.json"
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)
