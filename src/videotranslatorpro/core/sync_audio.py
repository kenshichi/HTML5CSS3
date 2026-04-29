from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def _probe_duration(path: str) -> float:
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], text=True).strip()
        return float(out)
    except Exception:
        return 0.0


def _adjust_segment(input_audio: str, output_audio: str, target_duration: float, max_speed: float = 1.35) -> Tuple[float, str]:
    d = _probe_duration(input_audio)
    if d <= 0:
        raise RuntimeError("Không đọc được thời lượng TTS")
    if d <= target_duration:
        subprocess.run(["ffmpeg", "-y", "-i", input_audio, "-c:a", "pcm_s16le", output_audio], check=True, capture_output=True, text=True)
        return d, "ok"

    speed = min(max_speed, d / max(target_duration, 0.01))
    cmd = ["ffmpeg", "-y", "-i", input_audio, "-filter:a", f"atempo={speed:.3f}", "-c:a", "pcm_s16le", output_audio]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    d2 = _probe_duration(output_audio)
    if d2 <= target_duration:
        return d2, "speedup"

    subprocess.run(["ffmpeg", "-y", "-i", output_audio, "-t", f"{target_duration:.3f}", "-c:a", "pcm_s16le", output_audio], check=True, capture_output=True, text=True)
    return target_duration, "trim"


def sync_tts_to_timeline(segments: List[Dict], video_path: str, output_dir: str, safety_gap: float = 0.15, mode: str = "Tự động cân thời lượng") -> Dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    temp = out / "sync_temp"
    temp.mkdir(parents=True, exist_ok=True)
    video_dur = _probe_duration(video_path)
    timeline = out / "final_vietnamese_voice.wav"

    seg_reports = []
    adjusted = []
    inputs = []
    for i, seg in enumerate(segments):
        src = seg.get("tts_path", "")
        if not src or not Path(src).exists():
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        next_start = float(segments[i+1].get("start", end)) if i < len(segments)-1 else end
        available = max(0.2, next_start - start - safety_gap) if i < len(segments)-1 else max(0.2, end - start)
        if mode == "Ưu tiên nghe tự nhiên":
            available += 0.10
        out_seg = temp / f"adj_{i:04d}.wav"
        dur, status = _adjust_segment(src, str(out_seg), available)
        seg_reports.append({"index": i+1, "start": start, "available_duration": available, "final_duration": dur, "status": status})
        adjusted.append(str(out_seg))
        inputs.extend(["-i", str(out_seg)])

    if not adjusted:
        raise RuntimeError("Chưa có tệp TTS hợp lệ để đồng bộ")

    mix_inputs = ["-f", "lavfi", "-t", f"{video_dur:.3f}", "-i", "anullsrc=r=24000:cl=mono"] + inputs
    parts = ["[0:a]"]
    for i, rep in enumerate(seg_reports, start=1):
        delay_ms = int(rep["start"] * 1000)
        parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[d{i}]")
    mix_refs = "".join([f"[d{i}]" for i in range(1, len(seg_reports)+1)])
    filter_complex = ";".join(parts[1:]) + f";[0:a]{mix_refs}amix=inputs={len(seg_reports)+1}:normalize=0[out]"
    cmd = ["ffmpeg", "-y", *mix_inputs, "-filter_complex", filter_complex, "-map", "[out]", "-c:a", "pcm_s16le", str(timeline)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    report = {
        "video_duration": video_dur,
        "timeline_audio": str(timeline),
        "segments": seg_reports,
        "safety_gap": safety_gap,
        "mode": mode,
    }
    (out / "sync_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def export_dubbed_video(video_path: str, vietnamese_audio_path: str, output_path: str, audio_mode: str, source_volume: int, vi_volume: int) -> str:
    vf = []
    if audio_mode == "Giữ âm thanh gốc":
        fc = f"[0:a]volume={source_volume/100:.2f}[bg];[1:a]volume={vi_volume/100:.2f}[vi];[bg][vi]amix=inputs=2:normalize=0[aout]"
    elif audio_mode == "Giảm âm lượng âm thanh gốc":
        fc = f"[0:a]volume={max(0.0,source_volume/200):.2f}[bg];[1:a]volume={vi_volume/100:.2f}[vi];[bg][vi]amix=inputs=2:normalize=0[aout]"
    else:
        fc = f"[1:a]volume={vi_volume/100:.2f}[aout]"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", vietnamese_audio_path, "-filter_complex", fc, "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", output_path]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path
