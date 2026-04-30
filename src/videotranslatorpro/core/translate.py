from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

LANG_TO_NLLB = {
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "th": "tha_Thai",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
}


def cleanup_vietnamese_text(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?]){2,}", r"\1", t)
    if t:
        t = t[0].upper() + t[1:]
    return t


def format_subtitle_text(text: str, max_chars_per_line: int = 42, max_lines: int = 2) -> str:
    words = text.split()
    lines, cur = [], []
    for w in words:
        if len(" ".join(cur + [w])) > max_chars_per_line and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:max_lines])


def _translate_with_nllb(texts: List[str], source_language: str) -> List[str]:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    model_name = "facebook/nllb-200-distilled-600M"
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    src = LANG_TO_NLLB.get(source_language, "eng_Latn")
    tok.src_lang = src
    inputs = tok(texts, return_tensors="pt", padding=True, truncation=True)
    out = model.generate(**inputs, forced_bos_token_id=tok.convert_tokens_to_ids("vie_Latn"), max_length=256)
    return tok.batch_decode(out, skip_special_tokens=True)


def _translate_with_argos(texts: List[str], source_language: str) -> List[str]:
    import argostranslate.translate
    langs = argostranslate.translate.get_installed_languages()
    src = next((l for l in langs if l.code == source_language), None)
    dst = next((l for l in langs if l.code == "vi"), None)
    if not src or not dst:
        raise RuntimeError("Argos chưa có model phù hợp")
    tr = src.get_translation(dst)
    return [tr.translate(t) for t in texts]


def translate_segments_to_vietnamese(segments: list, source_language: str, mode: str, experimental_mode: bool = False) -> Tuple[list, str]:
    rows = [dict(s) for s in segments]
    pending_idx = [i for i, s in enumerate(rows) if not s.get("manual_edited", False)]
    texts = [rows[i].get("source_text", "") for i in pending_idx]
    if not texts:
        return rows, ""

    warning = ""
    translated: List[str]
    try:
        translated = _translate_with_nllb(texts, source_language)
    except Exception:
        try:
            translated = _translate_with_argos(texts, source_language)
        except Exception:
            if experimental_mode:
                translated = [f"[Dịch thử nghiệm] {t}" for t in texts]
                warning = "[WARNING] Đang dùng chế độ dịch thử nghiệm, không phải bản dịch thật."
            else:
                return rows, "[WARNING] Chưa có mô hình dịch phù hợp. Vui lòng cài mô hình dịch hoặc bật chế độ dịch thử nghiệm."

    for j, idx in enumerate(pending_idx):
        vi = cleanup_vietnamese_text(translated[j])
        vi_sub = vi
        if mode == "Dịch ngắn cho lồng tiếng":
            vi_dub = vi[:100].rstrip() + ("..." if len(vi) > 100 else "")
        elif mode == "Dịch tự nhiên":
            vi_dub = vi[:120].rstrip() + ("..." if len(vi) > 120 else "")
        elif mode == "Giữ sát nghĩa":
            vi_dub = vi
        else:
            vi_dub = vi[:130].rstrip() + ("..." if len(vi) > 130 else "")
        rows[idx]["vi_subtitle_text"] = vi_sub
        rows[idx]["vi_dubbing_text"] = vi_dub
        rows[idx]["translation_status"] = "Đã dịch"
        rows[idx].setdefault("manual_edited", False)
    return rows, warning


def save_transcript_vi(output_dir: str, source_language: str, mode: str, original_segments: List[Dict], translated_segments: List[Dict]) -> str:
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    fp = p / "transcript_vi.json"
    fp.write_text(json.dumps({
        "source_language": source_language,
        "target_language": "vi",
        "translation_mode": mode,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "original_transcript": original_segments,
        "translated_transcript": translated_segments,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(fp)
