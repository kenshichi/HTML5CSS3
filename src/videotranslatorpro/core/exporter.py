from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess


def _ts_name(base: str, suffix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{suffix}_{ts}"


def export_final_project(project_state, output_goal, settings, progress_callback=None) -> dict:
    out = Path(settings.get("output_dir", "output")); out.mkdir(parents=True, exist_ok=True)
    video = Path(settings.get("input_video_path", ""))
    if progress_callback:
        progress_callback({"phase": "export", "percent": 5, "message": "Đang kiểm tra dữ liệu đầu vào..."})

    has_translation = project_state.get("has_translation", False)
    has_subtitle = project_state.get("has_subtitle", False)
    has_tts = project_state.get("has_tts", False)
    has_dub = project_state.get("has_dubbed_video", False)
    results = {"success": False, "goal": output_goal, "files": [], "error": ""}

    if output_goal == "Chỉ tạo phụ đề tiếng Việt":
        if not has_translation:
            results["error"] = "Chưa có bản dịch tiếng Việt. Hãy bấm 'Dịch sang tiếng Việt' trước."
            return results
        if not has_subtitle:
            results["error"] = "Chưa có phụ đề. Hãy bấm 'Tạo phụ đề' trước."
            return results
        for f in ["translated_vi.srt", "translated_vi.ass", "final_subtitled_video.mp4"]:
            fp = out / f
            if fp.exists(): results["files"].append(str(fp))

    elif output_goal == "Chỉ lồng tiếng tiếng Việt":
        if not has_translation:
            results["error"] = "Chưa có bản dịch tiếng Việt. Hãy bấm 'Dịch sang tiếng Việt' trước."; return results
        if not has_tts:
            results["error"] = "Chưa có giọng đọc. Hãy bấm 'Tạo giọng đọc' trước."; return results
        if not has_dub:
            results["error"] = "Chưa đồng bộ giọng đọc. Hãy bấm 'Đồng bộ & lồng tiếng' trước."; return results
        for f in ["final_vietnamese_voice.wav", "final_dubbed_video.mp4"]:
            fp = out / f
            if fp.exists(): results["files"].append(str(fp))

    elif output_goal == "Phụ đề + lồng tiếng tiếng Việt":
        if not (has_translation and has_subtitle and has_tts and has_dub):
            results["error"] = "Thiếu dữ liệu để xuất video đầy đủ. Vui lòng hoàn tất phụ đề và lồng tiếng."; return results
        if progress_callback:
            progress_callback({"phase": "export", "percent": 70, "message": "Đang kết xuất video cuối..."})
        subtitled = out / "final_subtitled_video.mp4"
        dubbed = out / "final_dubbed_video.mp4"
        full = out / "final_full_vietnamese_video.mp4"
        if subtitled.exists() and dubbed.exists():
            final_name = out / (_ts_name(video.stem or "video", "vi_full") + ".mp4")
            cmd = ["ffmpeg", "-y", "-i", str(subtitled), "-i", str(dubbed), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", str(final_name)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                results["files"].append(str(final_name))
            elif full.exists():
                results["files"].append(str(full))
        elif full.exists():
            results["files"].append(str(full))

    else:
        # transcript/srt
        for f in ["transcript_source.json", "transcript_vi.json", "translated_vi.srt"]:
            fp = out / f
            if fp.exists(): results["files"].append(str(fp))
        if not results["files"]:
            results["error"] = "Chưa có dữ liệu transcript để xuất."
            return results

    results["success"] = len(results["files"]) > 0
    if not results["success"] and not results["error"]:
        results["error"] = "Không thể xuất file."
    if progress_callback:
        progress_callback({"phase": "export", "percent": 100, "message": "Hoàn tất xuất file."})
    return results
