from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List


ERROR_MISSING_VI = "Chưa có bản dịch tiếng Việt. Vui lòng bấm 'Dịch sang tiếng Việt' trước khi tạo phụ đề."


def _safe_output_path(output_path: str) -> Path:
    p = Path(output_path)
    if not p.exists():
        return p
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")


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


def format_subtitle_text(text: str, max_chars_per_line: int = 42, max_lines: int = 2) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    words = [w for w in words if w]
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        cand = " ".join(current + [word]).strip()
        if len(cand) > max_chars_per_line and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return "\n".join(lines[:max_lines]).strip()


def _normalize_segments(segments: List[Dict]) -> List[Dict]:
    rows = [dict(s) for s in segments]
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
        row["_start"] = start
        row["_end"] = end
        row["_subtitle_text"] = format_subtitle_text(text)
    return rows


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def generate_srt(segments: list, output_path: str) -> str:
    rows = _normalize_segments(segments)
    valid = [r for r in rows if (r.get("_subtitle_text") or "").strip()]
    if not valid:
        raise ValueError(ERROR_MISSING_VI)
    out = _safe_output_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    chunks = []
    for idx, row in enumerate(valid, start=1):
        chunks.append(f"{idx}\n{_format_srt_time(row['_start'])} --> {_format_srt_time(row['_end'])}\n{row['_subtitle_text']}\n")
    out.write_text("\n".join(chunks), encoding="utf-8")
    return str(out)


def generate_ass(segments: list, output_path: str, style_settings: dict) -> str:
    rows = _normalize_segments(segments)
    valid = [r for r in rows if (r.get("_subtitle_text") or "").strip()]
    if not valid:
        raise ValueError(ERROR_MISSING_VI)
    out = _safe_output_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    font = style_settings.get("font", "Arial")
    size = int(style_settings.get("font_size", 36))
    primary = style_settings.get("text_color", "&H00FFFFFF")
    outline = style_settings.get("outline_color", "&H00000000")
    back = style_settings.get("back_color", "&H00000000")
    bold = -1 if style_settings.get("bold", False) else 0
    outline_width = float(style_settings.get("outline_width", 2.0))
    alignment = int(style_settings.get("position", 2))
    margin_v = int(style_settings.get("margin_v", 40))
    header = f"""[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,{font},{size},{primary},&H000000FF,{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_width},0,{alignment},40,40,{margin_v},1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    lines = [header]
    for row in valid:
        lines.append(f"Dialogue: 0,{_format_ass_time(row['_start'])},{_format_ass_time(row['_end'])},Default,,0,0,0,,{_escape_ass_text(row['_subtitle_text'])}")
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


def save_subtitle_settings(output_dir: str, settings: Dict) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fp = out / "subtitle_settings.json"
    fp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)
