from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional


def _probe_duration(path: str) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], text=True).strip())


def _atempo_chain(speed: float) -> str:
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    parts.append(f"atempo={max(0.5, min(2.0, speed)):.4f}")
    return ",".join(parts)


def sync_tts_to_timeline(video_path: str, segments: List[Dict], output_dir: str, max_speed: float = 1.25, safety_gap: float = 0.15, logger: Optional[Callable[[str], None]] = None):
    log = (lambda m: logger(m)) if logger else (lambda m: None)
    out = Path(output_dir)
    temp = out / "temp" / "tts_segments"
    temp.mkdir(parents=True, exist_ok=True)
    video_duration = _probe_duration(video_path)

    silent_base = temp / "silent_timeline.wav"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{video_duration:.3f}", str(silent_base)]
    log("FFmpeg command: " + " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    prepared = []
    plan = []
    for i, seg in enumerate(segments):
        tts = seg.get("tts_audio_path")
        if not tts or not Path(tts).exists():
            continue
        start = float(seg["start"])
        end = float(seg["end"])
        next_start = float(segments[i + 1]["start"]) if i + 1 < len(segments) else video_duration
        available = max(0.05, next_start - start - safety_gap)
        gen = _probe_duration(tts)
        req = max(1.0, gen / available)
        applied = min(req, max_speed)

        speed_out = temp / f"sync_{i:05d}.wav"
        cmd = ["ffmpeg", "-y", "-i", tts, "-af", _atempo_chain(applied), str(speed_out)]
        log("FFmpeg command: " + " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        trimmed = temp / f"trim_sil_{i:05d}.wav"
        cmd = ["ffmpeg", "-y", "-i", str(speed_out), "-af", "silenceremove=stop_periods=-1:stop_duration=0.08:stop_threshold=-45dB", str(trimmed)]
        log("FFmpeg command: " + " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        work = trimmed
        fixed = _probe_duration(str(work))
        if fixed > available:
            cut = temp / f"cut_{i:05d}.wav"
            cmd = ["ffmpeg", "-y", "-i", str(work), "-t", f"{available:.3f}", str(cut)]
            log("FFmpeg command: " + " ".join(cmd))
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            work = cut
            log(f"WARNING segment {i}: hard-cut to avoid overlap.")

        prepared.append((start, str(work)))
        plan.append({
            "id": i,
            "original_start": start,
            "original_end": end,
            "available_duration": available,
            "generated_tts_duration": gen,
            "required_speed_factor": req,
            "applied_speed_factor": applied,
        })

    if not prepared:
        raise RuntimeError("No TTS files to sync")

    inputs = ["-i", str(silent_base)]
    filters = []
    mix = ["[0:a]"]
    for idx, (start, p) in enumerate(prepared, start=1):
        inputs += ["-i", p]
        d = int(start * 1000)
        filters.append(f"[{idx}:a]adelay={d}|{d}[a{idx}]")
        mix.append(f"[a{idx}]")
    filter_complex = ";".join(filters) + ";" + "".join(mix) + f"amix=inputs={len(mix)}:normalize=0[m]"

    timeline = out / "temp" / "vi_tts_timeline.wav"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[m]", "-t", f"{video_duration:.3f}", str(timeline)]
    log("FFmpeg command: " + " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    (out / "sync_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return str(timeline), plan


def export_final_dubbed_video(video_path: str, tts_timeline_audio: str, output_path: str, original_audio_mode: str, original_audio_volume_percentage: int, vietnamese_voice_volume_percentage: int, logger: Optional[Callable[[str], None]] = None):
    log = (lambda m: logger(m)) if logger else (lambda m: None)
    ov = max(0, original_audio_volume_percentage) / 100.0
    vv = max(0, vietnamese_voice_volume_percentage) / 100.0
    if original_audio_mode in ["Mute original audio", "Tắt âm gốc", "Tắt âm thanh gốc"]:
        fc = f"[1:a]volume={vv}[outa]"
    else:
        orig = ov if original_audio_mode in ["Lower original audio volume", "Giảm âm lượng", "Giảm âm lượng gốc"] else 1.0
        fc = f"[0:a]volume={orig}[o];[1:a]volume={vv}[v];[o][v]amix=inputs=2:normalize=0[outa]"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", tts_timeline_audio, "-filter_complex", fc, "-map", "0:v", "-map", "[outa]", "-c:v", "copy", "-c:a", "aac", output_path]
    log("FFmpeg command: " + " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path
