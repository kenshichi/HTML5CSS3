# VideoTranslatorPro - Báo cáo trạng thái Phase (Audit)

> Audit dựa trên mã hiện tại trong `src/videotranslatorpro/ui/main_window.py` và các module core liên quan, **không thêm tính năng mới**.

## 1) Bảng trạng thái phase

| Phase | Trạng thái | Nhận xét ngắn |
|---|---|---|
| Phase UI/UX | PARTIAL | Có wizard/step, UI tiếng Việt; nhưng còn nút/luồng gây lỗi runtime ở một số nhánh. |
| Phase 2 metadata/audio extraction | PARTIAL | Đọc metadata + trích audio có gọi ffprobe/ffmpeg, nhưng phụ thuộc ffmpeg và có ràng buộc chưa kiểm soát hết lỗi. |
| Phase 3 transcription | PARTIAL | Có `transcribe_audio` + lưu transcript; hoạt động nếu môi trường có model/ffmpeg. |
| Phase 4 translation | DONE | Dịch NLLB/Argos fallback + lưu `transcript_vi.json`; có bảo toàn chỉnh tay. |
| Phase 5 subtitle generation | DONE | Tạo SRT/ASS + `subtitle_settings.json`, có fallback text và format dòng. |
| Phase 6 source subtitle detection | PARTIAL | Có heuristic + frame sample + json output; độ tin cậy thực tế phụ thuộc ảnh/môi trường. |
| Phase 7 subtitle video rendering | PARTIAL | Có burn ASS + mode che phụ đề; vẫn phụ thuộc ffmpeg/font/path thực tế. |
| Phase 8 TTS generation | PARTIAL | Tạo TTS theo đoạn + manifest, nhưng phụ thuộc internet Edge TTS. |
| Phase 9 dubbing sync | PARTIAL | Có timeline sync + anti-overlap + xuất dub, nhưng chưa có kiểm định robust nhiều case. |
| Phase 10 multi-speaker assignment | PARTIAL | Có sửa cột speaker và profile panel; chưa có load project ngược vào UI. |
| Phase 11 packaging | PLACEHOLDER | Có `build_windows.bat` mức cơ bản, chưa thấy workflow đóng gói/kiểm thử phát hành hoàn chỉnh. |

---

## 2) Chi tiết theo phase

## Phase UI/UX
- **Đã có**:
  - Main window + step list + trang workflow. 
  - Bind phần lớn nút chính. 
- **File/hàm chính**:
  - `src/videotranslatorpro/ui/main_window.py`: `_build_ui`, `_bind_events`, các `_page_*`.
- **Thiếu/Broken**:
  - `_export_debug()` gọi `self._sync_table_edits_to_segments()` nhưng không thấy định nghĩa trong class -> nguy cơ lỗi runtime khi bấm nút debug.
- **Nút kết nối**: phần lớn đã connect.
- **Output**: không áp dụng.
- **Acceptance**: chạy UI + bấm điều hướng cơ bản: đạt một phần.

## Phase 2 metadata/audio extraction
- **Đã có**:
  - `_read_video_metadata()` dùng ffprobe.
  - `_auto_analyze()` có `extract_audio(...)`.
- **File/hàm**:
  - `main_window.py`: `_read_video_metadata`, `_auto_analyze`.
  - `src/core/audio_extract.py`.
- **Thiếu/Broken**:
  - Phụ thuộc hoàn toàn ffmpeg/ffprobe trong PATH; lỗi môi trường chỉ log, chưa có wizard recovery.
- **Nút**: `Phân tích tự động` đã connect.
- **Output**: file audio tạm ở `temp/audio/...`.

## Phase 3 transcription
- **Đã có**:
  - `transcribe_audio(...)` + `save_transcript_json(...)`.
- **File/hàm**:
  - `src/videotranslatorpro/core/transcribe.py`.
  - `main_window.py` gọi trong `_auto_analyze()`.
- **Thiếu/Broken**:
  - Dựa vào model/runtime ngoài, chưa thấy cơ chế retry/profile download UX rõ.
- **Output**: `output/transcript_source.json`.

## Phase 4 translation
- **Đã có**:
  - `translate_segments_to_vietnamese(...)`.
  - NLLB -> Argos -> fallback source text + warning.
  - `save_transcript_vi(...)`.
- **Nút**:
  - `Dịch tất cả`, `Dịch lại đoạn đã chọn`, `Áp dụng chỉnh sửa` đều connect.
- **Output**: `output/transcript_vi.json`.
- **Acceptance**: end-to-end dịch cơ bản: đạt.

## Phase 5 subtitle generation
- **Đã có**:
  - `generate_srt`, `generate_ass`, `save_subtitle_settings`.
  - Chuẩn hóa time tránh overlap cơ bản.
- **Nút**:
  - `Tạo phụ đề SRT/ASS` đã connect.
- **Output**:
  - `output/translated_vi.srt`, `output/translated_vi.ass`, `output/subtitle_settings.json`.

## Phase 6 source subtitle detection
- **Đã có**:
  - `detect_source_subtitles(...)` với sampling frame và heuristic top/bottom.
- **Nút**:
  - `Kiểm tra phụ đề gốc` đã connect; `_auto_analyze` cũng gọi.
- **Output**:
  - `output/subtitle_detection.json`, `output/subtitle_detection_frames/*.jpg`.
- **Thiếu/Broken**:
  - Heuristic mỏng, không OCR; kết quả chỉ định hướng.

## Phase 7 subtitle video rendering
- **Đã có**:
  - `render_subtitled_video(...)`, `save_render_settings(...)`.
  - Mode skip khi chỉ xuất file rời.
- **Nút**:
  - `Kết xuất video phụ đề` đã connect.
- **Output**:
  - `output/final_subtitled_video.mp4` (hoặc timestamped), `output/render_settings.json`.
- **Thiếu/Broken**:
  - Chưa thấy xác thực mạnh cho font/path đặc biệt đa nền tảng.

## Phase 8 TTS generation
- **Đã có**:
  - `list_voices`, `synthesize_text`, `synthesize_segments` (edge-tts).
  - Fallback voice VN hardcoded.
- **Nút**:
  - `Nghe thử giọng`, `Tạo giọng đọc` đã connect.
- **Output**:
  - `temp/tts_segments/*.mp3`, `output/tts_manifest.json`.
- **Thiếu/Broken**:
  - Phụ thuộc internet Edge TTS; offline chưa có provider thật (Piper/XTTS mới là khung).

## Phase 9 dubbing sync
- **Đã có**:
  - `sync_tts_to_timeline(...)` tạo timeline wav + anti-overlap bằng speedup/trim.
  - `export_dubbed_video(...)` mix audio mode.
- **Nút**:
  - `Xuất lồng tiếng` đã connect.
- **Output**:
  - `output/final_vietnamese_voice.wav`, `output/final_dubbed_video.mp4`, `output/sync_report.json`.
- **Thiếu/Broken**:
  - Anti-overlap theo heuristic `atempo`/trim, chưa thấy handling đầy đủ extreme edge cases.

## Phase 10 multi-speaker assignment
- **Đã có**:
  - Cột speaker trong transcript cho sửa tay.
  - Speaker panel có số câu/tổng thời lượng/lần xuất hiện đầu.
  - Smart assign giọng + override.
  - Lưu project state: `output/project_state.json`.
- **Thiếu/Broken**:
  - Mới thấy **save**, chưa thấy luồng **load** project state vào UI hoàn chỉnh.

## Phase 11 packaging
- **Đã có**:
  - `build_windows.bat`, `requirements.txt`.
- **Trạng thái**:
  - PLACEHOLDER ở mức release-grade: chưa có kiểm chứng đóng gói/first-run automation/installer pipeline.

---

## 3) Hành vi placeholder/nguy hiểm cần lưu ý

1. **TTS fallback sang `source_text`** nếu thiếu `vi_dubbing_text`/`vi_subtitle_text`.
   - Có thể khiến giọng đọc không phải tiếng Việt dù pipeline hướng tiếng Việt.

2. **Nút debug có thể lỗi runtime**:
   - `_export_debug()` gọi hàm không thấy định nghĩa (`_sync_table_edits_to_segments`).

3. **Một số trạng thái thành công dựa vào điều kiện môi trường**:
   - ffmpeg/model/internet thiếu sẽ fail ở runtime nhưng có thể chỉ log warning/error muộn.

4. **Nút được bật sẵn theo UI** (không disable sớm theo state machine cứng).
   - Dù có check trong handler, UX vẫn cho phép click sớm rồi mới báo warning.

5. **Các option engine tương lai** (Piper/XTTS) mới là khung lựa chọn UI, chưa phải implementation đầy đủ.

---

## 4) Khuyến nghị phase tiếp theo (cụ thể)

**Nên làm ngay: Phase “Ổn định hóa vận hành” (hardening) trước khi thêm tính năng mới**

Ưu tiên thực hiện theo thứ tự:
1. **Fix luồng BROKEN**: bổ sung/điều chỉnh `_sync_table_edits_to_segments` hoặc bỏ gọi sai.
2. **Chuẩn hóa state machine UI**: disable/enable nút theo `has_transcript/has_translation/has_subtitle/has_tts`.
3. **Hoàn thiện project load**: thêm `load_project_json` đối xứng với `save_project_json`.
4. **TTS guardrail tiếng Việt**: cho phép user chọn rõ fallback sang source text hoặc bắt buộc tiếng Việt.
5. **E2E smoke test script** cho ffmpeg/path/model checks trước khi chạy workflow.

---

## 5) Kết luận ngắn

- Pipeline đã đi khá xa (đến sync/dub), nhưng nhiều phase ở trạng thái **PARTIAL** vì phụ thuộc môi trường và còn điểm runtime/brittle.
- Chưa nên coi “production-ready”; nên harden luồng hiện có trước khi mở phase tính năng tiếp theo.

## Cập nhật stabilization (2026-04-30)
- Đã chặn TTS fallback ngầm sang `source_text` trong luồng chuẩn.
- Đã bổ sung readiness check + disable button theo trạng thái workflow.
- Đã thêm `_sync_table_edits_to_segments()` để tránh crash ở `Xuất báo cáo lỗi`.
- Đã thêm kiểm tra tồn tại file trước khi ghi log thành công cho các bước xuất chính.
- Trạng thái tổng thể vẫn PARTIAL ở nhiều phase do phụ thuộc môi trường (ffmpeg/model/internet).

## Cập nhật Phase 4 (2026-04-30)
- Đã nối lại nút **Dịch sang tiếng Việt** cho toàn bộ transcript.
- Dịch thật ưu tiên NLLB/Argos; nếu thiếu model sẽ báo rõ thay vì copy source text.
- Thêm tùy chọn **Dịch thử nghiệm** (ghi log cảnh báo rõ ràng).
- `vi_subtitle_text`, `vi_dubbing_text`, `translation_status`, `manual_edited` được ghi đầy đủ khi dịch.
