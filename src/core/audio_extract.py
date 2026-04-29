from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class FFmpegNotFoundError(RuntimeError):
    pass


@dataclass
class AudioExtractionResult:
    success: bool
    output_wav_path: str
    used_stream_index: Optional[int]
    command: str
    error: str = ""


def extract_audio(input_video_path: str, output_wav_path: str, selected_audio_stream: Optional[int] = None) -> AudioExtractionResult:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise FFmpegNotFoundError("Thiếu ffmpeg. Vui lòng cài ffmpeg và thêm vào PATH.")

    out = Path(output_wav_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin, "-y", "-i", input_video_path]
    if selected_audio_stream is not None:
        cmd += ["-map", f"0:{selected_audio_stream}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return AudioExtractionResult(False, str(out), selected_audio_stream, " ".join(cmd), proc.stderr.strip())
    return AudioExtractionResult(True, str(out), selected_audio_stream, " ".join(cmd), "")
