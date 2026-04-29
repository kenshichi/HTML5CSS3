import subprocess
from typing import List


def run_ffmpeg_command(args: List[str]) -> subprocess.CompletedProcess:
    """Phase 1 wrapper around ffmpeg command execution."""
    command = ["ffmpeg", *args]
    return subprocess.run(command, check=False, capture_output=True, text=True)
