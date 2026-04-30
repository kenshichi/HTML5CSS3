from __future__ import annotations

VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (AI)", "engine": "edge_tts", "gender": "female"},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (AI)", "engine": "edge_tts", "gender": "male"},
    {"id": "vi_female_2", "name": "Google Female", "engine": "gtts", "gender": "female"},
    {"id": "vi_male_2", "name": "Offline Piper", "engine": "piper", "gender": "male"},
]


def as_display_items():
    return [{"id": v["id"], "display": v["name"]} for v in VOICES]
