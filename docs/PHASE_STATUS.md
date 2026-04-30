# VideoTranslatorPro - Báo cáo trạng thái phase (Audit thực tế)

> Ngày audit: 2026-04-30. Báo cáo này chỉ dựa trên mã hiện có, không dựa trên kế hoạch. Không thêm tính năng, không đổi hành vi.

## Tóm tắt nhanh

| Phase | Status | Can test now? | Main blocker |
|---|---|---|---|
| 1. UI/UX guided workflow | PARTIAL | Có | Luồng nhiều nút nhưng chưa có state-machine cứng cho toàn bộ bước |
| 2. Metadata / audio track / extract audio | PARTIAL | Có | Phụ thuộc ffprobe/ffmpeg; audio track detection thực tế chưa rõ ràng |
| 3. faster-whisper transcription | PARTIAL | Có | Phụ thuộc model + môi trường; có nhánh dùng cache thay vì ASR thật |
| 4. Vietnamese translation + cleanup | PARTIAL | Có | Chưa chứng minh cleanup mạnh; có fallback/ảnh hưởng môi trường model |
| 5. SRT/ASS generation | DONE | Có | Cần dữ liệu dịch hợp lệ |
| 6. Burned-in subtitle detection | PARTIAL | Có | Heuristic, không OCR đầy đủ |
| 7. Render subtitles into video | PARTIAL | Có | Phụ thuộc ffmpeg/font/video strategy |
| 8. Vietnamese TTS generation | PARTIAL | Có | Edge TTS cần internet; provider khác còn khung |
| 9. TTS sync + dubbed export | PARTIAL | Có | Cần manifest + ffmpeg + dữ liệu TTS đúng |
| 10. Multi-speaker + per-speaker voice | PARTIAL | Có | Cần user kiểm tra tay; chưa có validation sâu |
| 11. Optional auto diarization | PLACEHOLDER | Có (mức demo) | Provider tự động là tùy chọn, có nhánh placeholder |
| 12. Preview workflow | PARTIAL | Có | Phụ thuộc asset trung gian (sub/tts) |
| 13. Final export by output goal | PARTIAL | Có | Điều kiện goal phụ thuộc cờ state và file hiện có |
| 14. Caching / save-load / resume | PARTIAL | Có | Có save/load cơ bản nhưng chưa có fingerprint settings mạnh |
| 15. Environment checker + debug report | PARTIAL | Có | Chưa có màn hình checker riêng; debug report mức cơ bản |
| 16. Windows PyInstaller packaging | PARTIAL | Có | Có script build, chưa có bằng chứng test EXE runtime |
| 17. Final QA / release readiness | NOT IMPLEMENTED | Không | Chưa có bộ test/CI/release gate chính thức |

---

## 1) UI/UX guided workflow
**A. Status:** PARTIAL

**B. Evidence:**
- File chính: `src/videotranslatorpro/ui/main_window.py`.
- Có step list + workflow pages: `_build_ui`, `_page_video`, `_page_goal`, `_page_analysis`, `_page_review`, `_page_export`.
- Nút chính đã connect trong `_bind_events` (chọn video, phân tích, dịch, TTS, render, export, preview, save/load project, clear cache).
- Có cập nhật summary: `_refresh_export_summary`.

**C. Missing items / risk:**
- Không thấy cơ chế chặn sai luồng tuyệt đối cho mọi nút (phần lớn là warning khi click).
- Cần test UX ở nhiều nhánh lỗi (thiếu ffmpeg, thiếu internet, thiếu model).

**D. Acceptance test:**
1. Mở app, xem panel bước trái và 5 trang nội dung.
2. Bấm qua lại `◀ Quay lại`, `Tiếp theo ▶`.
3. Kiểm tra các nút chính hiển thị tiếng Việt.
- Kỳ vọng: UI mở được, không crash ngay; step list cập nhật khi đổi bước.

---

## 2) Phase 2: video metadata reading, audio track detection, audio extraction
**A. Status:** PARTIAL

**B. Evidence:**
- `_pick_video` + `_read_video_metadata` dùng `ffprobe`.
- `_auto_analyze` có gọi `extract_audio` từ `src/core/audio_extract.py`.
- Có lưu đường dẫn cache audio (`self.cache_status["extracted_audio"]`).

**C. Missing items / risk:**
- Không thấy bằng chứng chắc chắn audio track detection đầy đủ trong UI (chủ yếu `stream_idx` nếu có hàm chọn stream).
- Phụ thuộc ffmpeg/ffprobe PATH; fail sẽ dừng pipeline.

**D. Acceptance test:**
1. Chọn video bằng nút **Chọn video**.
2. Bấm **Phân tích tự động**.
- Kỳ vọng UI: hiện thời lượng/độ phân giải; log trích âm thanh.
- Output kỳ vọng: file WAV tạm dưới `temp/audio/`.

---

## 3) Phase 3: faster-whisper transcription
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/transcribe.py`: `transcribe_audio`, `save_transcript_json`.
- `_auto_analyze` gọi `transcribe_audio(...)` khi không có cache `transcript_source.json`.

**C. Missing items / risk:**
- Nếu có cache thì bỏ qua ASR thật (`[INFO] Đang dùng dữ liệu cache.`).
- Phụ thuộc model runtime; chưa có cơ chế quản lý model trong app theo kiểu robust.

**D. Acceptance test:**
1. Xóa `output/transcript_source.json`.
2. Bấm **Phân tích tự động**.
- Kỳ vọng: log tải/chạy Whisper; bảng transcript có dữ liệu.
- Output: `output/transcript_source.json`.

---

## 4) Phase 4: Vietnamese translation and text cleanup
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/translate.py`: `translate_segments_to_vietnamese`, `save_transcript_vi`.
- Nút connect: `Dịch sang tiếng Việt`, `Dịch lại đoạn đã chọn`, `Áp dụng chỉnh sửa`.
- `_translate_all` có dùng cache `transcript_vi.json` nếu tồn tại.

**C. Missing items / risk:**
- Cleanup văn bản có nhưng chưa có test coverage chứng minh chất lượng toàn cục.
- Chất lượng dịch phụ thuộc backend/model sẵn có.

**D. Acceptance test:**
1. Có transcript trước.
2. Bấm **Dịch sang tiếng Việt**.
- Kỳ vọng UI: cột bản dịch được điền.
- Output: `output/transcript_vi.json`.

---

## 5) Phase 5: SRT/ASS subtitle generation
**A. Status:** DONE

**B. Evidence:**
- `src/videotranslatorpro/core/subtitle.py`: `generate_srt`, `generate_ass`, `save_subtitle_settings`.
- UI: `_export_subtitles` gọi tạo SRT/ASS.

**C. Missing items / risk:**
- Vẫn cần test dữ liệu dịch lỗi/thiếu dòng dài.

**D. Acceptance test:**
1. Có bản dịch tiếng Việt.
2. Bấm **Xuất phụ đề SRT/ASS**.
- Output: `output/translated_vi.srt`, `output/translated_vi.ass`, `output/subtitle_settings.json`.
- UI: log `[OK]` tạo phụ đề.

---

## 6) Phase 6: burned-in subtitle detection and placement suggestion
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/subtitle_detection.py`: `detect_burned_in_subtitles`.
- UI: nút **Kiểm tra phụ đề gốc** gọi `_detect_source_subtitle`.

**C. Missing items / risk:**
- Cách làm heuristic, không OCR nặng => có thể sai ở video khó.

**D. Acceptance test:**
1. Chọn video.
2. Bấm **Kiểm tra phụ đề gốc**.
- Output: `output/subtitle_detection.json`, ảnh mẫu trong `output/subtitle_detection_frames/`.
- UI: card phát hiện phụ đề cập nhật.

---

## 7) Phase 7: render Vietnamese subtitles into video
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/render_video.py`: `render_subtitled_video`, `save_render_settings`.
- UI: `_render_subtitled_video` gọi render bằng ffmpeg.

**C. Missing items / risk:**
- Phụ thuộc ffmpeg và font hệ thống.
- Một số chiến lược phụ đề có thể không tối ưu cho mọi video.

**D. Acceptance test:**
1. Đảm bảo đã có `translated_vi.ass`.
2. Bấm **Kết xuất video phụ đề**.
- Output: `output/final_subtitled_video.mp4` + file settings render.
- UI: log thành công và đường dẫn file.

---

## 8) Phase 8: Vietnamese TTS generation
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/tts.py`: `list_voices`, `synthesize_text`, `synthesize_segments`.
- UI: nút **Nghe thử giọng**, **Tạo giọng đọc**.
- Tạo `tts_manifest.json` và segment files.

**C. Missing items / risk:**
- Edge TTS cần internet.
- Provider khác trong UI chưa phải implementation production đầy đủ.

**D. Acceptance test:**
1. Có bản dịch.
2. Bấm **Tạo giọng đọc**.
- Output: thư mục segment TTS + `output/tts_manifest.json`.
- UI: cột trạng thái TTS cập nhật.

---

## 9) Phase 9: TTS synchronization and dubbed video export
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/sync_audio.py`: `sync_tts_to_timeline`, `export_dubbed_video`.
- UI: `_sync_and_export_dubbed_video` gọi sync + mux.

**C. Missing items / risk:**
- Cần manifest hợp lệ và ffmpeg.
- Chưa có test tự động cho edge cases timeline.

**D. Acceptance test:**
1. Có `tts_manifest.json`.
2. Bấm **Xuất audio lồng tiếng**.
- Output: `output/final_vietnamese_voice.wav`, `output/final_dubbed_video.mp4`, `output/sync_report.json`.
- UI: log đồng bộ và xuất video.

---

## 10) Phase 10: multi-speaker management and per-speaker voice assignment
**A. Status:** PARTIAL

**B. Evidence:**
- Bảng speaker: tên hiển thị, voice, speed/pitch/volume.
- Hàm: `_fill_speaker_panel`, `_apply_speaker_table_to_segments`, `_auto_assign_speaker_voices`.
- Khi đổi speaker/voice có đánh dấu stale TTS.

**C. Missing items / risk:**
- Chất lượng phân tách speaker phụ thuộc dữ liệu và gán tay.
- Cần test kỹ tính nhất quán speaker giữa edit bảng và xuất TTS.

**D. Acceptance test:**
1. Sau transcript, chỉnh cột người nói hoặc bảng speaker.
2. Bấm **Áp dụng cho tất cả câu** rồi **Tạo giọng đọc**.
- UI: thấy cảnh báo cần tạo lại TTS khi đổi cấu hình giọng.

---

## 11) Phase 11: optional automatic speaker diarization
**A. Status:** PLACEHOLDER

**B. Evidence:**
- Có `PyannoteDiarizationProvider`/`ManualDiarizationProvider` trong core.
- `src/core/diarization.py` còn `auto_diarize_placeholder`.
- UI có nút **Tách người nói tự động**, nhưng nhánh fail được xử lý bằng warning.

**C. Missing items / risk:**
- Chưa có chứng cứ pipeline auto-diarization hoạt động ổn định trong môi trường mặc định.

**D. Acceptance test:**
1. Bấm **Tách người nói tự động** sau khi có transcript.
- Kỳ vọng: hoặc có mapping speaker, hoặc warning rõ ràng không crash.

---

## 12) Phase 12: preview workflow
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/preview.py`: `create_preview`.
- UI có loại preview + thời điểm/thời lượng + mở file/thư mục preview.

**C. Missing items / risk:**
- Kết quả phụ thuộc có sẵn phụ đề/tts tương ứng loại preview.

**D. Acceptance test:**
1. Chọn loại preview.
2. Bấm **Tạo preview**.
- Output: file trong `output/preview/`.
- UI: bật nút mở file preview khi tạo thành công.

---

## 13) Phase 13: final export workflow by output goal
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/exporter.py`: `export_final_project` theo goal.
- UI: `_export_final_by_goal` gọi exporter, log danh sách file.

**C. Missing items / risk:**
- Thành công phụ thuộc cờ state + file thực tế; chưa có checksum/validation sâu.

**D. Acceptance test:**
1. Chọn mục tiêu đầu ra.
2. Bấm **Xuất video hoàn chỉnh**.
- Kỳ vọng: log lỗi đúng khi thiếu bước; log file xuất khi đủ dữ liệu.

---

## 14) Phase 14: caching, project save/load, resume support
**A. Status:** PARTIAL

**B. Evidence:**
- `src/videotranslatorpro/core/project_state.py`: `ProjectState`, `save_project_state`, `load_project_state`, `missing_cache_files`.
- UI có nút: **Lưu dự án**, **Mở dự án**, **Làm lại bước này**, **Xóa cache dự án**.
- Có cache reuse ở `_auto_analyze` (transcript cache) và `_translate_all` (translation cache).

**C. Missing items / risk:**
- Chưa thấy cơ chế fingerprint đầy đủ để quyết định “settings unchanged” một cách chặt.
- Resume ở mức thực dụng, chưa phải transactional state recovery hoàn chỉnh.

**D. Acceptance test:**
1. Chạy đến sau dịch/TTS.
2. Bấm **Lưu dự án** (mặc định `output/project.json`).
3. Mở lại bằng **Mở dự án**.
- Kỳ vọng: transcript/speaker/state cơ bản được nạp lại.
4. Bấm **Xóa cache dự án**.
- Kỳ vọng: log `[OK] Đã xóa cache dự án.` và file trung gian bị xóa.

---

## 15) Phase 15: environment checker and debug report
**A. Status:** PARTIAL

**B. Evidence:**
- Có debug report: `_export_debug` (xuất thông tin app/python/ffmpeg).
- Không thấy màn hình “Kiểm tra môi trường” chuyên biệt trong UI hiện tại.

**C. Missing items / risk:**
- Thiếu preflight checker đầy đủ cho dependency/model/internet trước khi chạy pipeline.

**D. Acceptance test:**
1. Bấm **Xuất báo cáo lỗi**.
- Output: file text debug + snapshot json trong output.
- UI: log đã xuất báo cáo.

---

## 16) Phase 16: Windows PyInstaller packaging
**A. Status:** PARTIAL

**B. Evidence:**
- Có `build_windows.bat` gọi `pyinstaller`.
- Có `requirements.txt`.

**C. Missing items / risk:**
- Chưa có bằng chứng audit rằng EXE build xong chạy ổn ở máy sạch.
- Chưa thấy quy trình ký số/installer/rollback.

**D. Acceptance test:**
1. Trên Windows, cài đủ dependency.
2. Chạy `build_windows.bat`.
- Kỳ vọng output: thư mục `dist/...` với executable.

---

## 17) Phase 17: final QA and release readiness
**A. Status:** NOT IMPLEMENTED

**B. Evidence:**
- Không thấy test suite/CI release gate chính thức trong mã hiện tại.
- README có checklist thủ công, chưa phải release process có tự động hóa.

**C. Missing items / risk:**
- Chưa có regression test tự động cho các luồng chính.
- Chưa có tiêu chí pass/fail phát hành rõ ràng.

**D. Acceptance test:**
- Chưa có bộ acceptance chính thức ở mức release.

---

## End-to-end workflow status
1. **video -> transcription -> Vietnamese translation -> subtitle file -> subtitled video**: **CÓ THỂ**, nhưng **PARTIAL** do phụ thuộc ffmpeg/model/font và cần thao tác đúng thứ tự.
2. **video -> transcription -> Vietnamese translation -> TTS -> synced dubbed video**: **CÓ THỂ**, nhưng **PARTIAL** do phụ thuộc internet TTS + ffmpeg + manifest hợp lệ.
3. **multi-speaker voice assignment**: **CÓ** ở mức thực dụng (edit tay + apply profile), chưa có bảo đảm chất lượng tự động.
4. **build Windows .exe**: **CÓ SCRIPT BUILD**, chưa có bằng chứng audit rằng build luôn thành công và EXE chạy ổn trên máy sạch.

---

## Dangerous behaviors cần chú ý
- TTS có khả năng dùng text không như mong muốn nếu dữ liệu dịch thiếu/không hợp lệ (cần test thực tế từng nhánh).
- Subtitle có nguy cơ lấy dữ liệu không chuẩn nếu bản dịch rỗng hoặc chưa sync chỉnh sửa.
- Log thành công phụ thuộc file/nhánh; cần kiểm tra tồn tại file sau mỗi bước quan trọng.
- Một số nút có thể bấm khi dữ liệu chưa đủ (dù handler có warning).
- Thiếu dependency (ví dụ `PySide6`) khiến không chạy được `python app.py`.
- Trong codebase vẫn tồn tại module/hàm placeholder (`workflow.py`, `services/placeholders.py`, `auto_diarize_placeholder`).

---

## Current blockers (ưu tiên cao)
1. Thiếu dependency runtime trong môi trường thực thi sẽ chặn mở app (điển hình: `PySide6`).
2. Auto-diarization chưa đạt mức production (phase 11 chủ yếu placeholder/optional).
3. Chưa có preflight checker đầy đủ trước khi chạy pipeline dài.
4. Chưa có automated QA/release gate cho các luồng chính.

---

## Recommended next step
**Nên làm tiếp: Stabilization/QA hardening (Phase 17 thật sự) trước khi thêm tính năng mới.**

Lý do ngắn:
- Các phase chính đã có khung chạy được, nhưng độ tin cậy còn phụ thuộc môi trường và test tay.
- Giá trị lớn nhất tiếp theo là tăng tính ổn định phát hành: preflight checks, smoke tests E2E, tiêu chí release pass/fail rõ ràng.

---

## Kiểm tra `python app.py` trong môi trường audit
- `python -m py_compile ...` cho các file chính: **pass**.
- `python -c "import app"`: **fail** do thiếu `PySide6` trong môi trường audit hiện tại (không phải lỗi logic mới thêm trong lần cập nhật tài liệu).
