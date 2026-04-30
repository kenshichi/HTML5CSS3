from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import json
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


@dataclass
class ProjectState:
    input_video_path: str = ""
    output_folder: str = ""
    video_metadata: Dict[str, Any] = field(default_factory=dict)
    selected_audio_track: str = "auto"
    source_language: str = "auto"
    target_language: str = "vi"
    output_goal: str = ""
    transcript_segments: List[Dict[str, Any]] = field(default_factory=list)
    translations: List[Dict[str, Any]] = field(default_factory=list)
    speaker_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    subtitle_settings: Dict[str, Any] = field(default_factory=dict)
    subtitle_detection_result: Dict[str, Any] = field(default_factory=dict)
    tts_settings: Dict[str, Any] = field(default_factory=dict)
    tts_manifest: str = ""
    sync_settings: Dict[str, Any] = field(default_factory=dict)
    preview_files: List[str] = field(default_factory=list)
    final_export_paths: List[str] = field(default_factory=list)
    cache_status: Dict[str, Any] = field(default_factory=dict)
    workflow_state: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = _utc_now()
        return payload


def save_project_state(path: str | Path, state: ProjectState) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def load_project_state(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def missing_cache_files(payload: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for fp in payload.get("preview_files", []) + payload.get("final_export_paths", []):
        if fp and not Path(fp).exists():
            missing.append(fp)
    tts_manifest = payload.get("tts_manifest", "")
    if tts_manifest and not Path(tts_manifest).exists():
        missing.append(tts_manifest)
    for k, fp in payload.get("cache_status", {}).items():
        if isinstance(fp, str) and fp and not Path(fp).exists():
            missing.append(fp)
    return missing
