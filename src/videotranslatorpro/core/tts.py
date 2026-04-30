from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import subprocess

VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"
FALLBACK_VOICES = [
    {"id": VOICE_FEMALE, "display": "Hoài My - Nữ"},
    {"id": VOICE_MALE, "display": "Nam Minh - Nam"},
]


class TTSProvider(ABC):
    @abstractmethod
    def list_voices(self) -> List[Dict[str, str]]: ...

    @abstractmethod
    def synthesize_text(self, text: str, output_path: str, voice: str, speed: int, pitch: int, volume: int) -> str: ...

    @abstractmethod
    def synthesize_segments(self, segments, speaker_profiles, output_dir, default_voice, speed, pitch, volume): ...


class EdgeTTSProvider(TTSProvider):
    def list_voices(self) -> List[Dict[str, str]]:
        voices = list(FALLBACK_VOICES)
        try:
            import edge_tts
            for v in asyncio.run(edge_tts.list_voices()):
                short = v.get("ShortName", "")
                if short.startswith("vi-VN-") and all(x["id"] != short for x in voices):
                    gender = "Nữ" if v.get("Gender", "Female").lower().startswith("f") else "Nam"
                    voices.append({"id": short, "display": f"{v.get('FriendlyName', short)} - {gender}"})
        except Exception:
            pass
        return voices

    async def _synthesize_async(self, text: str, output_path: str, voice: str, speed: int, pitch: int, volume: int) -> None:
        import edge_tts
        rate = f"{max(-50, min(50, speed)):+d}%"
        pitch_s = f"{max(-100, min(100, pitch)):+d}Hz"
        vol = f"{max(-50, min(50, volume)):+d}%"
        await edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch_s, volume=vol).save(output_path)

    def synthesize_text(self, text: str, output_path: str, voice: str, speed: int, pitch: int, volume: int) -> str:
        if not text.strip():
            raise ValueError("empty_text")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._synthesize_async(text, output_path, voice, speed, pitch, volume))
        return output_path

    def synthesize_segments(self, segments, speaker_profiles, output_dir, default_voice, speed, pitch, volume):
        return synthesize_segments(segments, speaker_profiles, output_dir, default_voice, speed, pitch, volume)


def _duration_seconds(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], text=True).strip())
    except Exception:
        return 0.0


def _provider(name: str = "edge-tts") -> TTSProvider:
    return EdgeTTSProvider()


def list_voices(provider: str = "edge-tts") -> List[Dict[str, str]]:
    return _provider(provider).list_voices()


def synthesize_text(text: str, output_path: str, voice: str, speed: int = 0, pitch: int = 0, volume: int = 0, provider: str = "edge-tts") -> str:
    return _provider(provider).synthesize_text(text, output_path, voice, speed, pitch, volume)


def synthesize_segments(segments, speaker_profiles, output_dir, default_voice=VOICE_FEMALE, speed=0, pitch=0, volume=0, provider: str = "edge-tts") -> Dict:
    tts_dir = Path("temp") / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"provider": provider, "created_at": datetime.utcnow().isoformat() + "Z", "segments": []}

    for i, seg in enumerate(segments, start=1):
        spk = seg.get("speaker", "SPEAKER_01")
        prof = speaker_profiles.get(spk, {}) if speaker_profiles else {}
        voice = prof.get("voice", default_voice)
        spd = int(prof.get("speed", speed))
        pit = int(prof.get("pitch", pitch))
        vol = int(prof.get("volume", volume))
        text = (seg.get("vi_dubbing_text") or "").strip() or (seg.get("vi_subtitle_text") or "").strip()
        item = {"segment_id": i, "start": seg.get("start"), "end": seg.get("end"), "speaker": spk, "vi_dubbing_text": text, "voice": voice, "speed": spd, "pitch": pit, "volume": vol}
        if not text:
            seg["tts_status"] = "Bỏ qua, chưa có bản dịch"
            item["status"] = seg["tts_status"]
            manifest["segments"].append(item)
            continue
        out_fp = tts_dir / f"segment_{i:04d}.mp3"
        try:
            synthesize_text(text, str(out_fp), voice, spd, pit, vol, provider=provider)
            d = _duration_seconds(str(out_fp))
            seg.update({"tts_path": str(out_fp), "tts_duration": d, "tts_voice": voice, "tts_status": "Đã tạo giọng"})
            item.update({"tts_path": str(out_fp), "tts_duration": d, "status": "Đã tạo giọng"})
        except Exception as e:
            seg["tts_status"] = f"Lỗi: {e}"
            item["status"] = seg["tts_status"]
        manifest["segments"].append(item)

    out_manifest = Path(output_dir) / "tts_manifest.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(out_manifest)
    return manifest
