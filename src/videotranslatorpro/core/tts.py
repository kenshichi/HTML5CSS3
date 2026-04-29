from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Dict, List

VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"
FALLBACK_VOICES = [
    {"id": VOICE_FEMALE, "display": "Hoài My - Nữ"},
    {"id": VOICE_MALE, "display": "Nam Minh - Nam"},
]


class EdgeTTSProvider:
    def list_voices(self) -> List[Dict[str, str]]:
        voices = list(FALLBACK_VOICES)
        try:
            import edge_tts
            data = asyncio.run(edge_tts.list_voices())
            for v in data:
                short = v.get("ShortName", "")
                if short.startswith("vi-VN-") and all(x["id"] != short for x in voices):
                    gender = "Nữ" if v.get("Gender", "Female").lower().startswith("f") else "Nam"
                    voices.append({"id": short, "display": f"{v.get('FriendlyName', short)} - {gender}"})
        except Exception:
            pass
        return voices

    async def _synthesize_async(self, text: str, output_path: str, voice: str, rate: int, pitch: int, volume: int) -> None:
        import edge_tts
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=f"{rate:+d}%",
            pitch=f"{pitch:+d}Hz",
            volume=f"{volume:+d}%",
        )
        await communicate.save(output_path)

    def synthesize_text(self, text: str, output_path: str, voice: str, speed: int, pitch: int, volume: int) -> str:
        if not text.strip():
            raise ValueError("empty_text")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._synthesize_async(text, output_path, voice, speed, pitch, volume))
        return output_path


def _duration_seconds(path: str) -> float:
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], text=True).strip()
        return float(out)
    except Exception:
        return 0.0


def list_voices(provider: str = "edge-tts") -> List[Dict[str, str]]:
    if provider == "edge-tts":
        return EdgeTTSProvider().list_voices()
    return list(FALLBACK_VOICES)


def synthesize_text(text: str, output_path: str, voice: str, speed: int = 0, pitch: int = 0, volume: int = 0, provider: str = "edge-tts") -> str:
    if provider != "edge-tts":
        raise RuntimeError("Provider chưa được hỗ trợ ở giai đoạn này")
    return EdgeTTSProvider().synthesize_text(text, output_path, voice, speed, pitch, volume)


def synthesize_segments(segments: List[Dict], speaker_profiles: Dict[str, Dict], output_dir: str, provider: str = "edge-tts") -> Dict:
    tts_dir = Path("temp") / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"provider": provider, "segments": []}

    for i, seg in enumerate(segments, start=1):
        spk = seg.get("speaker", "SPEAKER_01")
        prof = speaker_profiles.get(spk, {})
        voice = prof.get("voice", VOICE_FEMALE)
        speed = int(prof.get("speed", 0))
        pitch = int(prof.get("pitch", 0))
        volume = int(prof.get("volume", 0))
        text = (seg.get("vi_dubbing_text") or "").strip() or (seg.get("vi_subtitle_text") or "").strip()
        fallback = False
        if not text:
            text = (seg.get("source_text") or "").strip()
            fallback = bool(text)
        item = {"index": i, "speaker": spk, "voice": voice, "fallback_source_text": fallback}
        if not text:
            seg["tts_status"] = "Bỏ qua: văn bản rỗng"
            item["tts_status"] = seg["tts_status"]
            manifest["segments"].append(item)
            continue
        out_fp = tts_dir / f"segment_{i:04d}.mp3"
        try:
            synthesize_text(text, str(out_fp), voice, speed, pitch, volume, provider=provider)
            dur = _duration_seconds(str(out_fp))
            seg["tts_path"] = str(out_fp)
            seg["tts_duration"] = dur
            seg["tts_status"] = "Đã tạo giọng"
            item.update({"tts_path": str(out_fp), "tts_duration": dur, "tts_status": seg["tts_status"]})
        except Exception as e:
            seg["tts_status"] = f"Lỗi: {e}"
            item["tts_status"] = seg["tts_status"]
        manifest["segments"].append(item)

    out_manifest = Path(output_dir) / "tts_manifest.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(out_manifest)
    return manifest
