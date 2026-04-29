from __future__ import annotations
from typing import Dict, List

DEFAULT_SPEAKER_PROFILES = {
    "SPEAKER_00": {"voice": "vi-VN-HoaiMyNeural", "speed": 0, "volume": 0},
    "SPEAKER_01": {"voice": "vi-VN-NamMinhNeural", "speed": 0, "volume": 0},
}


def ensure_speakers(segments: List[Dict]) -> List[Dict]:
    out = []
    for s in segments:
        row = dict(s)
        row["speaker"] = row.get("speaker") or "SPEAKER_00"
        out.append(row)
    return out


def collect_speakers(segments: List[Dict]) -> List[str]:
    return sorted({(s.get("speaker") or "SPEAKER_00") for s in segments})


def build_speaker_profiles(segments: List[Dict], existing: Dict[str, Dict] | None = None) -> Dict[str, Dict]:
    profiles = dict(existing or {})
    for sp in collect_speakers(segments):
        if sp not in profiles:
            profiles[sp] = dict(DEFAULT_SPEAKER_PROFILES.get(sp, {"voice": "vi-VN-HoaiMyNeural", "speed": 0, "volume": 0}))
    return profiles


def auto_diarize_placeholder(_: str):
    return {
        "enabled": False,
        "message": "Auto speaker detection is optional and may require pyannote.audio model setup.",
    }
