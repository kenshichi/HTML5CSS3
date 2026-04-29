from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegNotFoundError(RuntimeError):
    pass


def extract_audio_16k_mono(video_path: str, output_wav_path: str) -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise FFmpegNotFoundError("Không tìm thấy ffmpeg trong PATH. Vui lòng cài ffmpeg trước khi nhận diện.")

    output = Path(output_wav_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Trích xuất âm thanh bằng ffmpeg thất bại: {result.stderr.strip()}")
    return str(output)
