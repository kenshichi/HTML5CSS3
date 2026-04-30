from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List


def read_video_metadata(video_path: str) -> Dict:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe:
        if ffmpeg:
            raise RuntimeError("Không tìm thấy ffprobe. Vui lòng cài ffmpeg đầy đủ để đọc thông tin video chính xác.")
        raise RuntimeError("Không tìm thấy ffmpeg/ffprobe trong PATH.")

    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path]
    data = json.loads(subprocess.check_output(cmd, text=True))

    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    audios = [s for s in streams if s.get("codec_type") == "audio"]

    fps = "unknown"
    if v.get("r_frame_rate") and v.get("r_frame_rate") != "0/0":
        n, d = v["r_frame_rate"].split("/")
        fps = f"{float(n)/float(d):.2f}" if float(d) else "unknown"

    audio_tracks: List[Dict] = []
    for i, a in enumerate(audios, start=1):
        tags = a.get("tags", {})
        audio_tracks.append({
            "stream_index": a.get("index"),
            "track_no": i,
            "codec": a.get("codec_name", "unknown"),
            "language": tags.get("language", "unknown"),
            "channels": a.get("channels", "?"),
            "sample_rate": a.get("sample_rate", "?"),
            "duration": a.get("duration", data.get("format", {}).get("duration")),
            "title": tags.get("title", ""),
        })

    return {
        "file_name": Path(video_path).name,
        "full_path": video_path,
        "duration": float(data.get("format", {}).get("duration", 0.0)),
        "resolution": f"{v.get('width','?')} x {v.get('height','?')}",
        "fps": fps,
        "size": int(data.get("format", {}).get("size", 0)),
        "format": data.get("format", {}).get("format_name", "unknown"),
        "video_codec": v.get("codec_name", "unknown"),
        "audio_tracks": audio_tracks,
    }


def choose_audio_track(tracks: List[Dict], source_lang_code: str) -> int | None:
    if not tracks:
        return None
    for t in tracks:
        if t.get("language") == source_lang_code:
            return t["stream_index"]
    return tracks[0]["stream_index"]
