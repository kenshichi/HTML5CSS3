from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from faster_whisper import WhisperModel

from src.core.audio_extract import extract_audio_16k_mono


SUPPORTED_SOURCE_LANG = {"auto": None, "zh": "zh", "en": "en", "ja": "ja", "ko": "ko"}


def transcribe_video(
    video_path: str,
    output_folder: str,
    source_language: str = "auto",
    model_size: str = "small",
    compute_type: str = "int8",
) -> tuple[List[Dict], str | None]:
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_path = out_dir / "audio_16k_mono.wav"
    extract_audio_16k_mono(video_path, str(wav_path))

    language: Optional[str] = SUPPORTED_SOURCE_LANG.get(source_language, None)
    model = WhisperModel(model_size, compute_type=compute_type)
    segments, info = model.transcribe(str(wav_path), language=language, vad_filter=True)

    rows: List[Dict] = []
    for idx, seg in enumerate(segments):
        rows.append(
            {
                "id": idx,
                "start": float(seg.start),
                "end": float(seg.end),
                "source_text": seg.text.strip(),
                "speaker": "SPEAKER_00",
            }
        )

    transcript_path = out_dir / "transcript.json"
    payload = {"detected_language": info.language if info else language, "segments": rows}
    transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows, (info.language if info else language)
