from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

LANG_TO_NLLB = {
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
}
TARGET_VI = "vie_Latn"


def _normalize_vi_text(text: str) -> str:
    import re
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"([,.;:!?])\1+", r"\1", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])(\S)", r"\1 \2", t)
    if t:
        t = t[0].upper() + t[1:]
    return t


def _subtitle_linebreak(text: str, max_len: int = 42) -> str:
    words = text.split()
    lines, cur = [], []
    for w in words:
        cand = " ".join(cur + [w])
        if len(cand) > max_len and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:2])



def _protect_terms(text: str) -> Tuple[str, Dict[str, str]]:
    """Protect names, numbers, dates, technical/product/hotel-like terms with placeholders."""
    patterns = [
        r"\b\d+[\d,./:-]*\b",
        r"\b[A-Z][a-zA-Z0-9_-]{2,}\b",
        r"\b(?:Wi-?Fi|check-?in|check-?out|suite|deluxe|iPhone|Galaxy|USB|HDMI|CPU|GPU)\b",
    ]
    placeholders: Dict[str, str] = {}
    protected = text
    idx = 0
    for pat in patterns:
        for m in re.finditer(pat, protected):
            src = m.group(0)
            if src in placeholders.values():
                continue
            key = f"__TERM_{idx}__"
            placeholders[key] = src
            protected = protected.replace(src, key)
            idx += 1
    return protected, placeholders


def _restore_terms(text: str, placeholders: Dict[str, str]) -> str:
    out = text
    for key, value in placeholders.items():
        out = out.replace(key, value)
    return out


def translate_segments_to_vietnamese(
    segments: List[Dict],
    output_folder: str,
    source_language: str,
    translation_mode: str = "Dịch đầy đủ cho phụ đề",
    detected_language: str | None = None,
) -> Tuple[List[Dict], str]:
    lang = source_language if source_language != "auto" else (detected_language or "en")
    src_nllb = LANG_TO_NLLB.get(lang, "eng_Latn")

    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        model_name = "facebook/nllb-200-distilled-600M"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        warning = ""

        batch_size = 8
        translated: List[Dict] = []
        memory: Dict[str, str] = {}
        for i in range(0, len(segments), batch_size):
            batch = segments[i : i + batch_size]
            texts = []
            protections = []
            for seg in batch:
                ptxt, ph = _protect_terms(seg.get("source_text", ""))
                texts.append(ptxt)
                protections.append(ph)

            inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True)
            forced_bos_token_id = tokenizer.convert_tokens_to_ids(TARGET_VI)
            generated = model.generate(**inputs, forced_bos_token_id=forced_bos_token_id, max_length=256)
            outputs = tokenizer.batch_decode(generated, skip_special_tokens=True)

            for seg, vi, ph in zip(batch, outputs, protections):
                vi_full = _normalize_vi_text(_restore_terms(vi.strip(), ph))
                for k,v in memory.items():
                    if k in seg.get("source_text", ""):
                        vi_full = vi_full.replace(k, v)
                if translation_mode == "Dịch ngắn cho lồng tiếng":
                    vi_short = vi_full[:120].rstrip() + ("..." if len(vi_full) > 120 else "")
                elif translation_mode == "Dịch tự nhiên":
                    vi_short = vi_full
                elif translation_mode == "Giữ sát nghĩa":
                    vi_short = vi_full
                else:
                    vi_short = vi_full
                vi_full = _subtitle_linebreak(vi_full)
                row = dict(seg)
                row["vi_subtitle_text"] = vi_full
                row["vi_dubbing_text"] = vi_short
                translated.append(row)

    except Exception as ex:
        warning = f"WARNING: NLLB model unavailable, fallback to source text ({ex})"
        translated = []
        for seg in segments:
            row = dict(seg)
            src = seg.get("source_text", "")
            clean = _normalize_vi_text(src)
            row["vi_subtitle_text"] = _subtitle_linebreak(clean)
            row["vi_dubbing_text"] = clean if translation_mode != "Dịch ngắn cho lồng tiếng" else clean[:120]
            translated.append(row)

    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "translated_transcript.json"
    payload = {
        "source_language": lang,
        "source_nllb": src_nllb,
        "target_nllb": TARGET_VI,
        "translation_mode": translation_mode,
        "warning": warning,
        "segments": translated,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return translated, warning
