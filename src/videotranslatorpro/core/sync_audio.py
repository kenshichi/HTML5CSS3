from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


def _probe_duration(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], text=True).strip())
    except Exception:
        return 0.0


def _safe_video_path(output_video_path: str) -> Path:
    p = Path(output_video_path)
    if not p.exists():
        return p
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")


def _adjust_segment(input_audio: str, output_audio: str, available_duration: float, max_speech_speed: float) -> dict:
    original = _probe_duration(input_audio)
    if available_duration <= 0:
        available_duration = 0.2
    speed = min(max_speech_speed, max(1.0, original / max(available_duration, 0.01)))
    was_trimmed = False
    warning = ""
    cmd = ["ffmpeg", "-y", "-i", input_audio, "-filter:a", f"atempo={speed:.3f}", "-c:a", "pcm_s16le", output_audio]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    adjusted = _probe_duration(output_audio)
    if adjusted > available_duration:
        subprocess.run(["ffmpeg", "-y", "-i", output_audio, "-t", f"{available_duration:.3f}", "-c:a", "pcm_s16le", output_audio], check=True, capture_output=True, text=True)
        adjusted = available_duration
        was_trimmed = True
        warning = "Đã cắt để tránh đè tiếng."
    return {"original_tts_duration": original, "adjusted_tts_duration": adjusted, "speed_factor": round(speed, 3), "was_trimmed": was_trimmed, "warning": warning}


def sync_tts_to_timeline(video_path: str, segments: list, tts_manifest_path: str, output_audio_path: str, settings: dict) -> dict:
    out_audio = Path(output_audio_path)
    out_audio.parent.mkdir(parents=True, exist_ok=True)
    temp = Path("temp") / "tts_adjusted"
    temp.mkdir(parents=True, exist_ok=True)
    safety_gap = float(settings.get("safety_gap", 0.15))
    max_speed = float(settings.get("max_speech_speed", 1.25))
    mode = settings.get("timing_mode", "Tự động cân thời lượng")
    manifest = json.loads(Path(tts_manifest_path).read_text(encoding="utf-8")) if Path(tts_manifest_path).exists() else {"segments": []}

    rows, inputs, reports = [], [], []
    for i, seg in enumerate(segments, start=1):
        tts = seg.get("tts_path")
        if not tts or not Path(tts).exists():
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        next_start = float(segments[i].get("start", end)) if i < len(segments) else end
        available = (next_start - start - safety_gap) if i < len(segments) else (end - start)
        if mode == "Ưu tiên nghe tự nhiên":
            max_speed = min(max_speed, 1.15)
        adj = temp / f"segment_{i:04d}_adjusted.wav"
        met = _adjust_segment(tts, str(adj), available, max_speed)
        rep = {"segment_id": i, "speaker": seg.get("speaker"), "start": start, "end": end, "available_duration": available, "tts_input_path": tts, "tts_adjusted_path": str(adj), **met}
        reports.append(rep)
        inputs.extend(["-i", str(adj)])

    if not inputs:
        return {"success": False, "error": "Chưa có giọng đọc tiếng Việt.", "output_audio_path": "", "sync_report_path": ""}

    video_dur = _probe_duration(video_path)
    base = ["-f", "lavfi", "-t", f"{video_dur:.3f}", "-i", "anullsrc=r=24000:cl=mono"] + inputs
    delay_cmds = []
    for idx, rep in enumerate(reports, start=1):
        d = int(rep["start"] * 1000)
        delay_cmds.append(f"[{idx}:a]adelay={d}|{d}[d{idx}]")
    mix_refs = "".join([f"[d{i}]" for i in range(1, len(reports)+1)])
    filter_complex = ";".join(delay_cmds) + f";[0:a]{mix_refs}amix=inputs={len(reports)+1}:normalize=0[out]"
    cmd = ["ffmpeg", "-y", *base, "-filter_complex", filter_complex, "-map", "[out]", "-c:a", "pcm_s16le", str(out_audio)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr[-1000:], "output_audio_path": "", "sync_report_path": "", "ffmpeg_command": " ".join(cmd)}

    sync_report = {"created_at": datetime.utcnow().isoformat()+"Z", "segments": reports, "tts_manifest_path": tts_manifest_path}
    report_path = out_audio.parent / "sync_report.json"
    report_path.write_text(json.dumps(sync_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "output_audio_path": str(out_audio), "sync_report_path": str(report_path), "ffmpeg_command": " ".join(cmd), "error": ""}


def export_dubbed_video(input_video_path: str, vietnamese_voice_audio_path: str, output_video_path: str, original_audio_mode: str, original_audio_volume: float, vietnamese_voice_volume: float) -> dict:
    out = _safe_video_path(output_video_path)
    if original_audio_mode == "Giữ âm thanh gốc":
        fc = f"[0:a]volume=1.0[bg];[1:a]volume={vietnamese_voice_volume:.2f}[vi];[bg][vi]amix=inputs=2:normalize=0[aout]"
    elif original_audio_mode == "Giảm âm lượng âm thanh gốc":
        fc = f"[0:a]volume={original_audio_volume:.2f}[bg];[1:a]volume={vietnamese_voice_volume:.2f}[vi];[bg][vi]amix=inputs=2:normalize=0[aout]"
    else:
        fc = f"[1:a]volume={vietnamese_voice_volume:.2f}[aout]"
    cmd = ["ffmpeg", "-y", "-i", input_video_path, "-i", vietnamese_voice_audio_path, "-filter_complex", fc, "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"success": False, "output_path": "", "ffmpeg_command": " ".join(cmd), "error": r.stderr[-1000:]}
    return {"success": True, "output_path": str(out), "ffmpeg_command": " ".join(cmd), "error": ""}
