from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def _format_srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _normalize_segments(segments: List[Dict]) -> Tuple[List[Dict], bool]:
    rows = [dict(s) for s in segments]
    used_fallback = False
    for i, row in enumerate(rows):
        start = float(row.get("start", 0.0))
        end = float(row.get("end", start + 0.5))
        if i < len(rows) - 1:
            next_start = float(rows[i + 1].get("start", end + 1.0))
            if end >= next_start:
                end = next_start - 0.05
        if end <= start:
            end = start + 0.5
        text = (row.get("vi_subtitle_text") or "").strip()
        if not text:
            text = (row.get("source_text") or "").strip()
            if text:
                used_fallback = True
        row["_start"] = start
        row["_end"] = end
        row["_subtitle_text"] = format_subtitle_text(text)
    return rows, used_fallback


def format_subtitle_text(text: str, max_chars_per_line: int = 42, max_lines: int = 2) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    words = [w for w in words if w]
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if len(candidate) > max_chars_per_line and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return "\n".join(lines[:max_lines]).strip()


def _escape_ass_text(text: str) -> str:
    escaped = text.replace("\\", r"\\")
    escaped = escaped.replace("{", r"\{").replace("}", r"\}")
    return escaped.replace("\n", r"\N")


def generate_srt(segments: List[Dict], output_path: str) -> Tuple[str, str]:
    rows, used_fallback = _normalize_segments(segments)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    chunks: List[str] = []
    for idx, row in enumerate(rows, start=1):
        text = row.get("_subtitle_text", "")
        if not text:
            continue
        chunks.append(f"{idx}\n{_format_srt_time(row['_start'])} --> {_format_srt_time(row['_end'])}\n{text}\n")
    out.write_text("\n".join(chunks), encoding="utf-8")
    warning = "[WARNING] Một số câu chưa có tiếng Việt, tạm dùng văn bản gốc." if used_fallback else ""
    return str(out), warning


def generate_ass(segments: List[Dict], output_path: str, style_settings: Dict) -> Tuple[str, str]:
    rows, used_fallback = _normalize_segments(segments)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    font = style_settings.get("font", "Arial")
    size = int(style_settings.get("font_size", 44))
    primary = style_settings.get("text_color", "&H00FFFFFF")
    outline = style_settings.get("outline_color", "&H00000000")
    back = style_settings.get("back_color", "&H64000000")
    bold = -1 if style_settings.get("bold", False) else 0
    outline_width = float(style_settings.get("outline_width", 2.0))
    alignment = int(style_settings.get("position", 2))
    margin_v = int(style_settings.get("margin_v", 40))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},{size},{primary},&H000000FF,{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_width},0,{alignment},40,40,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    for row in rows:
        text = _escape_ass_text(row.get("_subtitle_text", ""))
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_format_ass_time(row['_start'])},{_format_ass_time(row['_end'])},Default,,0,0,0,,{text}"
        )
    out.write_text("\n".join(lines), encoding="utf-8")
    warning = "[WARNING] Một số câu chưa có tiếng Việt, tạm dùng văn bản gốc." if used_fallback else ""
    return str(out), warning


def save_subtitle_settings(output_dir: str, settings: Dict) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fp = out / "subtitle_settings.json"
    fp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)
