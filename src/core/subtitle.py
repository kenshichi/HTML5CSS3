from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass
class SubtitleStyle:
    font_file: str = ""
    font_name: str = "Arial"
    font_size: int = 36
    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    background_color: str = "#000000"
    background_opacity: int = 40
    bold: bool = False
    position: str = "bottom"  # top/middle/bottom
    margin_vertical: int = 40


@dataclass
class CoverBoxSettings:
    enabled: bool = False
    color: str = "yellow"
    height_percent: float = 0.18
    y_percent: float = 0.78


def _sec_to_srt(sec: float) -> str:
    ms = int(round(sec * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sec_to_ass(sec: float) -> str:
    cs = int(round(sec * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_ass_bgr(color: str) -> str:
    c = color.lstrip('#')
    if len(c) != 6:
        return "&H00FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}".upper()


def generate_srt(segments: List[Dict], out_path: str) -> str:
    p = Path(out_path)
    lines = []
    for i, seg in enumerate(segments, 1):
        txt = seg.get("vi_subtitle_text") or seg.get("source_text") or ""
        lines.extend([str(i), f"{_sec_to_srt(seg['start'])} --> {_sec_to_srt(seg['end'])}", txt, ""])
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def generate_ass(segments: List[Dict], out_path: str, style: SubtitleStyle) -> str:
    p = Path(out_path)
    alignment = {"bottom": 2, "middle": 5, "top": 8}.get(style.position, 2)
    primary = _hex_to_ass_bgr(style.text_color)
    outline = _hex_to_ass_bgr(style.outline_color)
    back = _hex_to_ass_bgr(style.background_color)
    bold = -1 if style.bold else 0
    alpha = max(0, min(255, int(255 * (100 - style.background_opacity) / 100)))
    back_alpha = f"&H{alpha:02X}"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{style.font_name},{style.font_size},{primary},&H000000FF,{outline},{back_alpha}{back[2:]},{bold},0,0,0,100,100,0,0,1,2,0,{alignment},30,30,{style.margin_vertical},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for seg in segments:
        txt = (seg.get("vi_subtitle_text") or seg.get("source_text") or "").replace("\n", "\\N")
        events.append(f"Dialogue: 0,{_sec_to_ass(seg['start'])},{_sec_to_ass(seg['end'])},Default,,0,0,0,,{txt}")
    p.write_text(header + "\n".join(events), encoding="utf-8-sig")
    return str(p)


def render_subtitled_video(
    input_video: str,
    ass_file: str,
    output_video: str,
    cover_settings: CoverBoxSettings,
    logger: Optional[Callable[[str], None]] = None,
) -> str:
    def log(msg: str):
        if logger:
            logger(msg)

    inp = Path(input_video)
    ass = Path(ass_file)
    out = Path(output_video)

    ass_escaped = str(ass).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
    vf = f"ass='{ass_escaped}'"
    if cover_settings.enabled:
        drawbox = (
            f"drawbox=x=0:y=ih*{cover_settings.y_percent}:w=iw:h=ih*{cover_settings.height_percent}:"
            f"color={cover_settings.color}:t=fill"
        )
        vf = f"{drawbox},{vf}"

    cmd = [
        "ffmpeg", "-y", "-i", str(inp), "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy", str(out),
    ]
    log("FFmpeg command: " + " ".join(f'"{c}"' if ' ' in c else c for c in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return str(out)
