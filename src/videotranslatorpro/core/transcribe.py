from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from faster_whisper import WhisperModel

LANG_MAP = {
    "Tự động phát hiện": None,
    "Tiếng Trung": "zh",
    "Tiếng Anh": "en",
    "Tiếng Nhật": "ja",
    "Tiếng Hàn": "ko",
    "Tiếng Thái": "th",
    "Tiếng Pháp": "fr",
    "Tiếng Đức": "de",
    "Tiếng Tây Ban Nha": "es",
    "Khác": None,
    "auto": None,
}

@dataclass
class TranscriptionResult:
    detected_language: Optional[str]
    segments: List[Dict]


def transcribe_audio(audio_path: str, language: str = "auto", model_size: str = "tiny", compute_type: str = "int8", device: str = "auto") -> TranscriptionResult:
    lang = LANG_MAP.get(language, None)
    model = WhisperModel(model_size, compute_type=compute_type, device=device)
    segs, info = model.transcribe(audio_path, language=lang, vad_filter=True)
    rows: List[Dict] = []
    idx = 1
    for s in segs:
        txt = (s.text or "").strip()
        if not txt:
            continue
        st = float(s.start); en = float(s.end)
        if en <= st:
            continue
        rows.append({
            "id": idx,
            "start": st,
            "end": en,
            "speaker": "SPEAKER_01",
            "source_text": txt,
            "vi_subtitle_text": "",
            "vi_dubbing_text": "",
            "translation_status": "Chưa dịch",
            "tts_status": "Chưa tạo giọng",
            "manual_edited": False,
        })
        idx += 1
    return TranscriptionResult(info.language if info else lang, rows)


def save_transcript_json(output_dir: str, video_metadata: Dict, selected_audio_track: str, source_language: str, model_size: str, compute_type: str, segments: List[Dict]) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "transcript_source.json"
    payload = {
        "video_metadata": video_metadata,
        "selected_audio_track": selected_audio_track,
        "selected_source_language": source_language,
        "whisper_settings": {"model_size": model_size, "compute_type": compute_type},
        "segments": segments,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
