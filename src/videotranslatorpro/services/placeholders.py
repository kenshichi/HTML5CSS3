from typing import List, Dict


def placeholder_transcribe(video_path: str) -> List[Dict]:
    """Return demo ASR segments for UI preview."""
    return [
        {"start": "00:00:01.200", "end": "00:00:04.800", "speaker": "SPEAKER_01", "text": "[ASR placeholder]"},
        {"start": "00:00:05.000", "end": "00:00:08.500", "speaker": "SPEAKER_02", "text": "[ASR placeholder]"},
    ]


def placeholder_translate(segments: List[Dict]) -> List[Dict]:
    """Return demo translated segments for UI preview."""
    result = []
    for seg in segments:
        row = dict(seg)
        row["translated_text"] = "[Bản dịch tiếng Việt placeholder]"
        result.append(row)
    return result


def placeholder_tts_plan(segments: List[Dict]) -> List[Dict]:
    """Return demo tts scheduling output for overlap-safe planner."""
    return [{**seg, "tts_status": "pending", "playback_rate": 1.0} for seg in segments]
