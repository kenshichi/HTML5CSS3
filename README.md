# VideoTranslatorPro

Professional Windows desktop app (PySide6) for translating videos into Vietnamese using free/open-source tools.

## Run from source
1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure ffmpeg is installed and in PATH.
4. Run:
   ```bash
   python app.py
   ```

## Build EXE (Windows)
Use PyInstaller one-folder build:
```bat
build_windows.bat
```
Output executable:
- `dist/VideoTranslatorPro/VideoTranslatorPro.exe`

### Packaging notes
- `src`, `assets`, and `fonts` are included in build.
- Do **not** bundle huge AI models inside EXE.
- Download/select models at runtime into `models/` (or user-selected path).

## First-run setup screen
The app shows a first-run setup dialog that checks:
- Python dependencies
- ffmpeg availability
- faster-whisper model folder
- NLLB model folder
- edge-tts runtime note

## Install ffmpeg on Windows
### Option A (winget)
```powershell
winget install Gyan.FFmpeg
```
### Option B (manual)
1. Download FFmpeg static build.
2. Extract to e.g. `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to system PATH.
4. Re-open terminal and test:
   ```powershell
   ffmpeg -version
   ```

## Common errors & fixes
- **`ffmpeg not found`**: add ffmpeg `bin` folder to PATH.
- **`Vietnamese TTS requires internet when using edge-tts.`**: connect to internet or skip dubbing.
- **Missing faster-whisper / NLLB model**: place models in `models/faster-whisper` and `models/nllb-200-distilled-600M` or select model location in app workflow.
- **PyInstaller import issue**: reinstall dependencies and rebuild.

## End-to-end validation checklist (Windows)
Use this checklist before shipping:

1. **Run from source**
   - `python app.py` launches UI without crash.
2. **Environment checks**
   - Click **Check Environment** and confirm ffmpeg/imports/output write permission.
3. **Pipeline smoke test**
   - Select a short test video.
   - Run Transcribe -> Translate -> Generate TTS.
   - Run subtitle render (`translated.srt`, `translated.ass`, `final_subtitled_video.mp4`).
   - Run Sync+Dub (`final_dubbed_video.mp4`).
4. **Debug tools**
   - Confirm `output/logs/app.log` is generated.
   - Export debug report and verify metadata + log tail.
5. **Packaging**
   - Run `build_windows.bat`.
   - Confirm `dist/VideoTranslatorPro/VideoTranslatorPro.exe` exists.
6. **Packaged app smoke test**
   - Launch EXE.
   - First-run setup dialog appears.
   - Open video and run at least one export path.
7. **Model policy check**
   - Verify large models are not bundled in `dist/`.
   - Models are downloaded/selected externally under `models/`.

## Giao diện tiếng Việt (Phase 1A)
- Toàn bộ giao diện đã Việt hóa: nhãn, nút, tiêu đề, bảng, hộp thoại và thông báo.
- Bố cục được tách theo tab: Chung, Nhận diện giọng nói, Dịch, Phụ đề, Lồng tiếng, Xuất file.
- Thiết kế tối ưu hiển thị cho 1366x768, 1600x900, 1920x1080 và scale 100/125/150%.

## Checklist QA & ổn định cuối (Windows)
Trước khi bàn giao bản phát hành, kiểm tra nhanh:

1. Chạy ứng dụng từ mã nguồn:
   - `python app.py`
2. Kiểm tra giao diện tiếng Việt:
   - Không còn nhãn tiếng Anh gây lẫn.
   - Không có text bị cắt ở 1366x768, 1600x900, 1920x1080.
3. Chọn video và xác nhận metadata hiển thị đúng:
   - Tên tệp, Thời lượng, Độ phân giải, Đường dẫn.
4. Chạy nhận diện (ASR) với Whisper:
   - Có log tiếng Việt rõ ràng.
   - Bảng transcript hiển thị đầy đủ cột.
5. Kiểm tra phụ đề:
   - Xuất `translated.srt`, `translated.ass`, `final_subtitled_video.mp4`.
6. Kiểm tra lồng tiếng:
   - Tạo file TTS theo từng đoạn.
   - Đồng bộ và xuất `final_dubbed_video.mp4`.
7. Kiểm tra thông báo lỗi:
   - Thiếu ffmpeg phải báo tiếng Việt dễ hiểu.
   - edge-tts mất mạng phải báo đúng.
8. Build EXE:
   - Chạy `build_windows.bat`.
   - Xác nhận `dist/VideoTranslatorPro/VideoTranslatorPro.exe`.
9. Chạy thử EXE sau build:
   - Mở được UI, không crash khi mở tab/chọn file.

## Phase 3 - Nhận diện lời nói (Whisper)
- Bấm **Phân tích tự động** để tự trích âm thanh 16kHz mono và chạy nhận diện lời nói.
- Model Whisper:
  - `tiny/base`: nhanh hơn
  - `small/medium`: chính xác hơn nhưng chậm hơn
- Kết quả lưu tại: `output/transcript_source.json`

### Lỗi thường gặp
- Không thể tải model Whisper: kiểm tra mạng hoặc chọn model nhỏ hơn.
- Thiếu ffmpeg: cài ffmpeg và thêm vào PATH.
- Không nhận diện được lời thoại: kiểm tra track âm thanh nguồn hoặc chất lượng âm thanh.

## Phase 5 - Tạo phụ đề tiếng Việt (SRT/ASS)

### Cách tạo phụ đề
1. Chạy ứng dụng: `python app.py`.
2. Chọn video, bấm **Phân tích tự động** để tạo transcript.
3. Ở bước kiểm tra, bấm **Dịch tất cả** để tạo bản dịch tiếng Việt.
4. Chuyển sang bước xuất file, bấm **Tạo phụ đề SRT/ASS**.
5. Kết quả sẽ được lưu trong thư mục output:
   - `translated_vi.srt`
   - `translated_vi.ass`
   - `subtitle_settings.json`

### Khác nhau giữa SRT và ASS
- **SRT**: định dạng đơn giản, tương thích rất rộng, phù hợp khi cần phụ đề cơ bản.
- **ASS**: hỗ trợ kiểu chữ, viền, nền, vị trí hiển thị tốt hơn; phù hợp khi cần kiểm soát giao diện phụ đề.

### Tuỳ chỉnh kiểu phụ đề (ASS)
- Có thể chọn **Font chữ**, **Cỡ chữ**, **In đậm**, **Vị trí phụ đề**, **Khoảng cách mép video**.
- Ở **Chế độ nhanh**, ứng dụng dùng mặc định an toàn cho tiếng Việt.
- Ở **Chế độ nâng cao**, tuỳ chỉnh sẽ được lưu vào `subtitle_settings.json` để tái sử dụng.

## Phase 6 - Phát hiện phụ đề gốc và gợi ý vị trí phụ đề Việt
- Tính năng phát hiện phụ đề gốc là **heuristic** (phỏng đoán theo ảnh mẫu), không dùng OCR nặng.
- Có thể bấm **Kiểm tra phụ đề gốc** hoặc dùng **Phân tích tự động** để chạy luôn.
- Ứng dụng lấy mẫu khung hình và lưu tại `output/subtitle_detection_frames/`, kết quả JSON tại `output/subtitle_detection.json`.
- Nếu độ tin cậy thấp, ứng dụng sẽ cảnh báo kiểm tra thủ công.

### Ghi đè thủ công
Bạn có thể tự chỉnh:
- Chiến lược phụ đề.
- Vị trí phụ đề Việt.
- Bật/tắt che phụ đề cũ.
- Màu vùng che, chiều cao vùng che, vị trí vùng che.

### Lưu ý chế độ thay thế (che phụ đề)
- Khi dùng chế độ **Che phụ đề gốc và thay bằng phụ đề Việt**, nên kiểm tra kỹ ảnh mẫu để tránh che nhầm nội dung quan trọng.
- Giai đoạn này chỉ tạo file phụ đề và cấu hình, chưa render vào video.

## Phase 7 - Kết xuất video có phụ đề tiếng Việt
### Cách kết xuất
1. Tạo phụ đề SRT/ASS trước.
2. Chọn chiến lược phụ đề (khuyên dùng: **Tự động, khuyên dùng**).
3. Bấm **Kết xuất video phụ đề**.
4. Kết quả tại `output/final_subtitled_video.mp4` (nếu trùng tên sẽ tự thêm timestamp).

### Chế độ che/thay phụ đề gốc
- Chọn **Che phụ đề gốc và thay bằng phụ đề Việt** để vẽ vùng che trước khi burn phụ đề ASS.
- Có thể chỉnh màu che, chiều cao vùng che và vị trí vùng che.
- Ứng dụng giữ nguyên audio gốc (`-c:a copy`).

### Lưu ý font tiếng Việt
- Nên dùng font hỗ trợ đầy đủ tiếng Việt (ví dụ Arial, Tahoma, Segoe UI, Noto Sans).
- Nếu font không hỗ trợ tiếng Việt, dấu có thể hiển thị sai khi burn phụ đề.

## Phase 8 - Tạo giọng đọc tiếng Việt (TTS)
- Engine mặc định: **edge-tts** (cần internet để tổng hợp giọng).
- Giọng fallback tích hợp sẵn:
  - `vi-VN-HoaiMyNeural` (Hoài My - Nữ)
  - `vi-VN-NamMinhNeural` (Nam Minh - Nam)

### Cách nghe thử giọng
1. Chọn **Giọng đọc mặc định**.
2. Chỉnh **Tốc độ đọc / Cao độ / Âm lượng giọng Việt**.
3. Nhập **Văn bản nghe thử**.
4. Bấm **Nghe thử giọng**.

### Cách tạo giọng theo từng đoạn
1. Hoàn tất bước dịch tiếng Việt.
2. Bấm **Tạo giọng đọc**.
3. Mỗi đoạn sẽ tạo một file tại `temp/tts_segments/`.
4. Manifest kết quả tại `output/tts_manifest.json`.

> Lưu ý: Giai đoạn này chưa đồng bộ/mux giọng vào video cuối.

## Phase 9 - Đồng bộ giọng đọc và xuất video lồng tiếng
### Chế độ đồng bộ
- **Tự động cân thời lượng**: tự tăng tốc khi cần để khớp timeline.
- **Ưu tiên khớp thời gian gốc**: cố bám mốc transcript chặt hơn.
- **Ưu tiên nghe tự nhiên**: cho phép nới thêm thời lượng trước khi tăng tốc.

### Logic chống đè tiếng
- Mỗi đoạn TTS được đặt tại `start` của transcript.
- Tính `available_duration` theo đoạn kế tiếp và `safety_gap`.
- Nếu quá dài: tăng tốc (`atempo`), vẫn quá dài thì cắt ngắn để tránh chồng lấn.

### Chế độ âm thanh gốc
- **Giữ âm thanh gốc**
- **Giảm âm lượng âm thanh gốc**
- **Tắt âm thanh gốc**

Có thể chỉnh:
- Âm lượng âm thanh gốc
- Âm lượng giọng Việt

### Tệp đầu ra
- `output/final_vietnamese_voice.wav`
- `output/final_dubbed_video.mp4`
- `output/sync_report.json`

## Phase 10 - Quản lý đa người nói và gán giọng theo người nói
- Cột **Người nói** trong bảng transcript có thể chỉnh tay (`SPEAKER_01`, `SPEAKER_02`, nhãn tuỳ chỉnh...).
- Bảng người nói hiển thị: mã người nói, tên hiển thị, số câu, tổng thời lượng, lần xuất hiện đầu tiên, giọng, tốc độ, cao độ, âm lượng.
- Nút **Tự gán giọng thông minh**:
  - 1 người nói: dùng giọng mặc định
  - 2 người nói: chia Nam/Nữ
  - >2 người nói: luân phiên giọng và tinh chỉnh nhẹ tốc độ/cao độ
- Khi tạo TTS, mỗi đoạn dùng giọng theo người nói tương ứng.
- Trạng thái dự án được lưu vào `output/project_state.json` gồm transcript, speaker profiles, subtitle settings và dubbing settings.
