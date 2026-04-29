from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SubtitleStyle:
    position: str = "bottom"
    font_family: str = "Arial"
    font_size: int = 36
    text_color: str = "#FFFFFF"
    background_color: str = "#000000"
    background_opacity: int = 55
    cover_old_subtitles: bool = False


@dataclass
class DubbingSettings:
    voice_male: str = "vi-VN-NamMinhNeural"
    voice_female: str = "vi-VN-HoaiMyNeural"
    speed: int = 0
    volume: int = 0
    original_audio_mode: str = "keep"


@dataclass
class AppSettings:
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    dubbing: DubbingSettings = field(default_factory=DubbingSettings)
    speaker_voice_map: Dict[str, str] = field(default_factory=dict)
