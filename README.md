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
