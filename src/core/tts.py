from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, List



VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"


def _percent_to_edge(value: int) -> str:
    if value == 0:
        return "+0%"
    return f"{value:+d}%"


async def _synthesize_to_file(text: str, voice: str, rate: int, volume: int, pitch: int, out_file: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=_percent_to_edge(rate),
        volume=_percent_to_edge(volume),
        pitch=f"{pitch:+d}Hz",
    )
    await communicate.save(out_file)


def synthesize_segments(
    segments: List[Dict],
    output_dir: str,
    default_voice: str,
    speed: int = 0,
    volume: int = 0,
    pitch: int = 0,
    speaker_profiles: Dict[str, Dict] | None = None,
) -> List[Dict]:
    tts_dir = Path(output_dir) / "temp" / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict] = []
    for i, seg in enumerate(segments):
        text = (seg.get("vi_dubbing_text") or seg.get("vi_subtitle_text") or "").strip()
        out_file = tts_dir / f"seg_{i:05d}.mp3"
        spk = seg.get("speaker", "SPEAKER_00")
        profile = (speaker_profiles or {}).get(spk, {})
        use_voice = profile.get("voice", default_voice)
        use_speed = int(profile.get("speed", speed))
        use_volume = int(profile.get("volume", volume))
        if text:
            asyncio.run(_synthesize_to_file(text, use_voice, use_speed, use_volume, pitch, str(out_file)))
        row = dict(seg)
        row["tts_audio_path"] = str(out_file)
        results.append(row)
    return results


def synthesize_preview(text: str, output_dir: str, voice: str, speed: int = 0, volume: int = 0, pitch: int = 0) -> str:
    preview_dir = Path(output_dir) / "temp" / "tts_segments"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_file = preview_dir / "voice_preview.mp3"
    asyncio.run(_synthesize_to_file(text, voice, speed, volume, pitch, str(out_file)))
    return str(out_file)
