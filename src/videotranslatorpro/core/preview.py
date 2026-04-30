from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def _safe_preview_path(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        return p
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")


def _ass_filter(path: str) -> str:
    return "ass='" + str(Path(path)).replace("\\", "/").replace(":", "\\:").replace("'", "\\'") + "'"


def create_preview(input_video_path: str, output_preview_path: str, start_time: float, duration: float, preview_type: str, subtitle_ass_path: str | None, dubbed_audio_path: str | None, subtitle_strategy: str, cover_settings: dict, settings: dict, progress_callback=None) -> dict:
    out = _safe_preview_path(output_preview_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback({"phase": "preview", "percent": 5, "message": "Đang chuẩn bị preview..."})

    if preview_type == "Preview phụ đề":
        if not subtitle_ass_path or not Path(subtitle_ass_path).exists():
            return {"success": False, "error": "Chưa có phụ đề. Vui lòng tạo phụ đề trước."}
        cmd = ["ffmpeg", "-y", "-ss", f"{start_time:.3f}", "-i", input_video_path, "-t", f"{duration:.3f}", "-vf", _ass_filter(subtitle_ass_path), "-c:v", "libx264", "-c:a", "copy", str(out)]
    elif preview_type == "Preview lồng tiếng":
        if not dubbed_audio_path or not Path(dubbed_audio_path).exists():
            return {"success": False, "error": "Chưa có giọng lồng tiếng. Vui lòng tạo và đồng bộ giọng đọc trước."}
        cmd = ["ffmpeg", "-y", "-ss", f"{start_time:.3f}", "-i", input_video_path, "-ss", f"{start_time:.3f}", "-i", dubbed_audio_path, "-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", str(out)]
    else:
        if not subtitle_ass_path or not Path(subtitle_ass_path).exists():
            return {"success": False, "error": "Chưa có phụ đề. Vui lòng tạo phụ đề trước."}
        if not dubbed_audio_path or not Path(dubbed_audio_path).exists():
            return {"success": False, "error": "Chưa có giọng lồng tiếng. Vui lòng tạo và đồng bộ giọng đọc trước."}
        cmd = ["ffmpeg", "-y", "-ss", f"{start_time:.3f}", "-i", input_video_path, "-ss", f"{start_time:.3f}", "-i", dubbed_audio_path, "-t", f"{duration:.3f}", "-vf", _ass_filter(subtitle_ass_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "aac", str(out)]

    if progress_callback:
        progress_callback({"phase": "preview", "percent": 50, "message": "Đang cắt đoạn video..."})
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr[-1000:], "ffmpeg_command": " ".join(cmd)}
    if progress_callback:
        progress_callback({"phase": "preview", "percent": 100, "message": "Đã tạo preview."})
    return {"success": True, "output_path": str(out), "ffmpeg_command": " ".join(cmd), "error": ""}
