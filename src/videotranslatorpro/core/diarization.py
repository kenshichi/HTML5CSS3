from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.core.diarization import build_speaker_profiles as _build_profiles, ensure_speakers as _ensure_speakers


class DiarizationProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def diarize(self, audio_path: str, settings: dict, progress_callback=None) -> dict: ...


class ManualDiarizationProvider(DiarizationProvider):
    def is_available(self) -> bool:
        return True

    def diarize(self, audio_path: str, settings: dict, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback({"phase": "diarization", "percent": 100, "message": "Gán thủ công đang được dùng."})
        return {"success": True, "provider": "manual", "speakers": [], "segments": [], "warnings": ["Gán thủ công đang được dùng."]}


class PyannoteDiarizationProvider(DiarizationProvider):
    def is_available(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            return True
        except Exception:
            return False

    def diarize(self, audio_path: str, settings: dict, progress_callback=None) -> dict:
        if not self.is_available():
            return {"success": False, "provider": "pyannote", "error": "Tính năng tách người nói tự động cần cài thêm pyannote.audio và mô hình phù hợp. Hiện tại bạn có thể gán người nói thủ công.", "warnings": []}
        token = settings.get("pyannote_token", "")
        if not token:
            return {"success": False, "provider": "pyannote", "error": "Chưa cấu hình mô hình tách người nói. Vui lòng xem hướng dẫn trong README.", "warnings": []}
        return {"success": False, "provider": "pyannote", "error": "Chưa tích hợp pipeline pyannote đầy đủ trong bản này.", "warnings": ["Tách người nói tự động có thể chưa chính xác."]}


def map_diarization_to_transcript(transcript_segments: list, diarization_segments: list) -> list:
    rows = [dict(x) for x in transcript_segments]
    for row in rows:
        s0, e0 = float(row.get("start", 0.0)), float(row.get("end", 0.0))
        best, who = 0.0, row.get("speaker", "SPEAKER_01")
        for d in diarization_segments:
            s1, e1 = float(d.get("start", 0.0)), float(d.get("end", 0.0))
            ov = max(0.0, min(e0, e1) - max(s0, s1))
            if ov > best:
                best, who = ov, d.get("speaker", who)
        row["speaker"] = who if best > 0 else row.get("speaker", "Không chắc")
    return rows


def save_diarization_output(output_dir: str, result: dict, mapped_segments: list) -> str:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    payload = {**result, "mapped_transcript": mapped_segments, "created_at": datetime.utcnow().isoformat() + "Z"}
    fp = out / "diarization.json"
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)


build_speaker_profiles = _build_profiles
ensure_speakers = _ensure_speakers
