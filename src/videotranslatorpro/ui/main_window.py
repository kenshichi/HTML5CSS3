from __future__ import annotations

import importlib.util
import json
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import *

from src.core.audio_extract import FFmpegNotFoundError
from src.core.diarization import auto_diarize_placeholder, build_speaker_profiles, ensure_speakers
from src.core.subtitle import CoverBoxSettings, SubtitleStyle, generate_ass, generate_srt, render_subtitled_video
from src.core.sync_audio import export_final_dubbed_video, sync_tts_to_timeline
from src.core.transcribe import transcribe_video
from src.core.translate import translate_segments_to_vietnamese
from src.core.tts import VOICE_FEMALE, VOICE_MALE, synthesize_preview, synthesize_segments
from src.videotranslatorpro import __version__


class FirstRunSetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập lần đầu")
        self.resize(760, 460)
        layout = QVBoxLayout(self)
        self.info = QLabel("Ứng dụng sẽ kiểm tra môi trường chạy cơ bản. Mô hình lớn không đi kèm file .exe.")
        self.list_widget = QListWidget()
        btn_row = QHBoxLayout()
        self.btn_check = QPushButton("Kiểm tra lại")
        self.btn_ok = QPushButton("Tiếp tục")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_check.clicked.connect(self.run_checks)
        btn_row.addWidget(self.btn_check)
        btn_row.addWidget(self.btn_ok)
        btn_row.addStretch(1)
        layout.addWidget(self.info)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)

    def run_checks(self) -> None:
        self.list_widget.clear()
        checks = []
        for m in ["PySide6", "faster_whisper", "transformers", "edge_tts"]:
            checks.append((f"Thư viện Python: {m}", importlib.util.find_spec(m) is not None))
        checks.append(("ffmpeg trong PATH", shutil.which("ffmpeg") is not None))
        checks.append(("Mô hình faster-whisper (models/faster-whisper)", (Path("models") / "faster-whisper").exists()))
        checks.append(("Mô hình NLLB (models/nllb-200-distilled-600M)", (Path("models") / "nllb-200-distilled-600M").exists()))
        for name, ok in checks:
            self.list_widget.addItem(f"{'✅' if ok else '⚠️'} {name}")
        self.list_widget.addItem("ℹ️ edge-tts có thể cần Internet khi tạo giọng nói.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoTranslatorPro")
        self.resize(1500, 920)
        self.setMinimumSize(1200, 700)
        self.setFont(QFont("Segoe UI", 10))

        self.selected_video_path = ""
        self.detected_language = None
        self.current_segments: List[Dict[str, Any]] = []
        self.speaker_profiles: Dict[str, Dict[str, Any]] = {}
        self.debug_mode = True
        self._setup_logger()
        self._build_ui()
        self._load_stylesheet()
        self._bind_events()
        self._show_first_run_setup()

    def _setup_logger(self) -> None:
        log_dir = Path("output") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / "app.log"
        logging.basicConfig(filename=str(self.log_file), level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        self.logger = logging.getLogger("VideoTranslatorPro")

    def _show_first_run_setup(self) -> None:
        dlg = FirstRunSetupDialog(self)
        dlg.run_checks()
        dlg.exec()

    def _build_ui(self) -> None:
        root = QWidget()
        main = QHBoxLayout(root)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(10)

        sidebar = self._build_sidebar()
        right = self._build_right_panel()

        main.addWidget(sidebar)
        main.addWidget(right, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Sidebar")
        frame.setMinimumWidth(250)
        v = QVBoxLayout(frame)
        v.addWidget(QLabel("🎬 VideoTranslatorPro"))
        self.steps = QListWidget()
        self.steps.addItems([
            "1. Chọn video", "2. Nhận diện", "3. Dịch", "4. Phụ đề", "5. Lồng tiếng", "6. Giọng nhân vật", "7. Xuất file"
        ])
        v.addWidget(self.steps)
        v.addStretch(1)
        return frame

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.addWidget(self._build_top_info())

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_settings_area())
        splitter.addWidget(self._build_table_area())
        splitter.setSizes([420, 320])
        v.addWidget(splitter, 1)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText("Nhật ký xử lý...")
        self.log.setMaximumHeight(140)
        v.addWidget(self.log)
        return wrap

    def _build_top_info(self) -> QWidget:
        top = QFrame(); g = QGridLayout(top)
        self.file_name = QLineEdit("Chưa chọn video"); self.file_name.setReadOnly(True)
        self.file_duration = QLineEdit("--:--:--"); self.file_duration.setReadOnly(True)
        self.file_resolution = QLineEdit("---- x ----"); self.file_resolution.setReadOnly(True)
        self.input_path = QLineEdit("--"); self.input_path.setReadOnly(True)
        self.output_folder = QLineEdit(str(Path.cwd() / "output")); self.output_folder.setReadOnly(True)
        self.btn_video = QPushButton("Chọn video")
        self.btn_output = QPushButton("Chọn thư mục xuất")
        g.addWidget(QLabel("Tên tệp"), 0, 0); g.addWidget(self.file_name, 0, 1, 1, 3); g.addWidget(self.btn_video, 0, 4)
        g.addWidget(QLabel("Thời lượng"), 1, 0); g.addWidget(self.file_duration, 1, 1)
        g.addWidget(QLabel("Độ phân giải"), 1, 2); g.addWidget(self.file_resolution, 1, 3)
        g.addWidget(QLabel("Đường dẫn"), 2, 0); g.addWidget(self.input_path, 2, 1, 1, 4)
        g.addWidget(QLabel("Thư mục đầu ra"), 3, 0); g.addWidget(self.output_folder, 3, 1, 1, 3); g.addWidget(self.btn_output, 3, 4)
        return top

    def _build_settings_area(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._tab_common(), "Chung")
        tabs.addTab(self._tab_asr(), "Nhận diện giọng nói")
        tabs.addTab(self._tab_translate(), "Dịch")
        tabs.addTab(self._tab_subtitle(), "Phụ đề")
        tabs.addTab(self._tab_tts(), "Lồng tiếng")
        tabs.addTab(self._tab_export(), "Xuất file")
        return tabs

    def _form_tab(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget(); f = QFormLayout(w); f.setLabelAlignment(Qt.AlignRight); f.setSpacing(8); return w, f

    def _tab_common(self) -> QWidget:
        w, f = self._form_tab()
        self.source_lang = QComboBox(); self.source_lang.addItems(["auto", "zh", "en", "ja", "ko"])
        self.export = QComboBox(); self.export.addItems(["MP4 video", "SRT only", "ASS only", "Audio only"])
        f.addRow("Ngôn ngữ nguồn", self.source_lang)
        f.addRow("Định dạng xuất", self.export)
        return w

    def _tab_asr(self) -> QWidget:
        w, f = self._form_tab()
        self.model_size = QComboBox(); self.model_size.addItems(["tiny", "base", "small", "medium"])
        self.compute_type = QComboBox(); self.compute_type.addItems(["int8", "float16", "float32"])
        f.addRow("Whisper model", self.model_size)
        f.addRow("Compute type", self.compute_type)
        return w

    def _tab_translate(self) -> QWidget:
        w, f = self._form_tab()
        self.translation_style = QComboBox(); self.translation_style.addItems(["Dịch đầy đủ cho phụ đề", "Dịch ngắn cho lồng tiếng"])
        f.addRow("Chế độ dịch", self.translation_style)
        return w

    def _tab_subtitle(self) -> QWidget:
        w, f = self._form_tab()
        self.font_name = QLineEdit("Arial"); self.font_size = QLineEdit("36")
        self.text_color = QLineEdit("#000000"); self.outline_color = QLineEdit("#000000")
        self.bg_color = QLineEdit("#000000"); self.bg_opacity = QLineEdit("40")
        self.sub_pos = QComboBox(); self.sub_pos.addItems(["top", "middle", "bottom"])
        self.bold = QComboBox(); self.bold.addItems(["off", "on"])
        self.cover_enabled = QComboBox(); self.cover_enabled.addItems(["off", "on"])
        self.cover_color = QLineEdit("yellow")
        f.addRow("Phông chữ", self.font_name); f.addRow("Cỡ chữ", self.font_size)
        f.addRow("Màu chữ", self.text_color); f.addRow("Màu viền", self.outline_color)
        f.addRow("Màu nền", self.bg_color); f.addRow("Độ mờ nền", self.bg_opacity)
        f.addRow("Vị trí phụ đề", self.sub_pos); f.addRow("In đậm", self.bold); f.addRow("Che phụ đề cũ", self.cover_enabled); f.addRow("Màu vùng che", self.cover_color)
        return w

    def _tab_tts(self) -> QWidget:
        w, f = self._form_tab()
        self.tts_voice = QComboBox(); self.tts_voice.addItems([VOICE_FEMALE, VOICE_MALE])
        self.tts_speed = QLineEdit("0"); self.tts_volume = QLineEdit("0"); self.tts_pitch = QLineEdit("0")
        self.max_speech_speed = QLineEdit("1.25"); self.safety_gap = QLineEdit("0.15")
        self.orig_audio_mode = QComboBox(); self.orig_audio_mode.addItems(["Giữ nguyên", "Giảm âm lượng", "Tắt âm gốc"])
        self.orig_audio_pct = QLineEdit("70"); self.vi_voice_pct = QLineEdit("100")
        self.tts_test_text = QLineEdit("Xin chào, đây là đoạn thử giọng tiếng Việt.")
        f.addRow("Giọng mặc định", self.tts_voice); f.addRow("Tốc độ", self.tts_speed); f.addRow("Âm lượng", self.tts_volume); f.addRow("Cao độ", self.tts_pitch)
        f.addRow("Tốc độ nói tối đa", self.max_speech_speed); f.addRow("Khoảng nghỉ an toàn", self.safety_gap)
        f.addRow("Chế độ âm thanh gốc", self.orig_audio_mode); f.addRow("Âm lượng âm thanh gốc", self.orig_audio_pct); f.addRow("Âm lượng giọng Việt", self.vi_voice_pct)
        f.addRow("Câu thử giọng", self.tts_test_text)
        return w

    def _tab_export(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        grid = QGridLayout()
        self.btn_start = QPushButton("Bắt đầu nhận diện")
        self.btn_translate = QPushButton("Dịch (Phase sau)")
        self.btn_tts = QPushButton("Tạo giọng đọc")
        self.btn_sync_dub = QPushButton("Đồng bộ & lồng tiếng (Phase sau)")
        self.btn_render = QPushButton("Kết xuất phụ đề")
        self.btn_test_voice = QPushButton("Thử giọng")
        self.btn_check_env = QPushButton("Kiểm tra môi trường")
        self.btn_export_debug = QPushButton("Xuất báo cáo lỗi")
        self.btn_cancel = QPushButton("Hủy")
        self.btn_export_project = QPushButton("Xuất Project JSON")
        self.btn_import_project = QPushButton("Nhập Project JSON")
        buttons = [self.btn_start, self.btn_translate, self.btn_tts, self.btn_sync_dub, self.btn_test_voice, self.btn_render, self.btn_check_env, self.btn_export_debug, self.btn_cancel, self.btn_export_project, self.btn_import_project]
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // 2, i % 2)
        v.addLayout(grid)
        self.progress = QProgressBar(); self.progress.setValue(0)
        v.addWidget(self.progress)
        return w

    def _build_table_area(self) -> QWidget:
        w = QWidget(); h = QHBoxLayout(w)
        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Người nói", "Văn bản gốc", "Bản dịch tiếng Việt"])
        self.table.horizontalHeader().setStretchLastSection(True)
        h.addWidget(self.table, 2)

        right = QGroupBox("Giọng theo người nói")
        rv = QVBoxLayout(right)
        self.speaker_table = QTableWidget(0, 4)
        self.speaker_table.verticalHeader().setDefaultSectionSize(32)
        self.speaker_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.speaker_table.setHorizontalHeaderLabels(["Nhân vật", "Giọng đọc", "Tốc độ", "Âm lượng"])
        self.btn_apply_speaker = QPushButton("Áp dụng cấu hình giọng")
        self.btn_auto_diar = QPushButton("Tách người nói tự động (tùy chọn)")
        self.lbl_diar = QLabel("Tách người nói tự động là tùy chọn và có thể cần cấu hình pyannote.audio.")
        rv.addWidget(self.speaker_table)
        rv.addWidget(self.btn_apply_speaker)
        rv.addWidget(self.btn_auto_diar)
        rv.addWidget(self.lbl_diar)
        h.addWidget(right, 1)
        return w

    def _bind_events(self) -> None:
        self.btn_video.clicked.connect(self._pick_video)
        self.btn_output.clicked.connect(self._pick_output)
        self.btn_start.clicked.connect(self._run_transcription)
        self.btn_cancel.clicked.connect(lambda: self._log("Đã hủy thao tác hiện tại."))
        self.btn_translate.clicked.connect(self._run_translation)
        self.btn_tts.clicked.connect(self._run_tts)
        self.btn_sync_dub.clicked.connect(self._sync_and_export_dubbed)
        self.btn_render.clicked.connect(self._render_subtitles)
        self.btn_test_voice.clicked.connect(self._test_voice)
        self.btn_check_env.clicked.connect(self._check_environment)
        self.btn_export_debug.clicked.connect(self._export_debug_report)
        self.btn_export_project.clicked.connect(self._export_project_json)
        self.btn_import_project.clicked.connect(self._import_project_json)
        self.btn_apply_speaker.clicked.connect(self._apply_speaker_profiles)
        self.btn_auto_diar.clicked.connect(self._auto_diarize_info)

    def _pick_video(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Chọn video", "", "Video Files (*.mp4 *.mkv *.avi *.mov)")
        if not p:
            return
        self.selected_video_path = p
        self.file_name.setText(Path(p).name)
        self.input_path.setText(p)
        try:
            meta = self._read_video_metadata(p)
            self.file_duration.setText(meta["duration"])
            self.file_resolution.setText(meta["resolution"])
            self._log(f"Đã chọn video: {p}")
        except Exception as e:
            self.file_duration.setText("Không đọc được")
            self.file_resolution.setText("Không đọc được")
            self._log(f"Cảnh báo: Không thể đọc metadata video ({e}).")

    def _read_video_metadata(self, video_path: str) -> Dict[str, str]:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        out = subprocess.check_output(cmd, text=True).strip().splitlines()
        if len(out) < 3:
            raise RuntimeError("Thiếu dữ liệu ffprobe")
        width, height, dur = out[0], out[1], float(out[2])
        h = int(dur // 3600); m = int((dur % 3600) // 60); s = int(dur % 60)
        return {"duration": f"{h:02d}:{m:02d}:{s:02d}", "resolution": f"{width} x {height}"}

    def _pick_output(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất")
        if p:
            self.output_folder.setText(p)
            self._log(f"Thư mục xuất: {p}")

    # Keep backend flow unchanged
    def _run_transcription(self) -> None:
        if not self.selected_video_path:
            self._log("Vui lòng chọn video trước.")
            return
        try:
            self._log("Bắt đầu nhận diện: trích xuất âm thanh 16kHz mono WAV...")
            self._log(f"Model Whisper: {self.model_size.currentText()} | Compute: {self.compute_type.currentText()} | Ngôn ngữ: {self.source_lang.currentText()}")
            segs, lang = transcribe_video(
                self.selected_video_path,
                self.output_folder.text().strip(),
                self.source_lang.currentText(),
                self.model_size.currentText(),
                self.compute_type.currentText(),
            )
            self._log("Đã nhận diện xong, đang cập nhật bảng transcript...")
            self.current_segments = ensure_speakers(segs)
            self.detected_language = lang
            self.speaker_profiles = build_speaker_profiles(self.current_segments, self.speaker_profiles)
            self._fill_table(self.current_segments)
            self._refresh_speaker_panel()
            self._log(f"Hoàn tất nhận diện: {len(segs)} đoạn. Đã lưu transcript.json trong thư mục đầu ra.")
        except FFmpegNotFoundError as e:
            self._log(f"LỖI ffmpeg: {e}")
        except Exception as e:
            self._log(f"LỖI nhận diện: {e}")

    def _run_translation(self) -> None:
        self._log("Phase 2 hiện chỉ triển khai nhận diện giọng nói. Chức năng dịch sẽ mở ở Phase sau.")

    def _run_tts(self) -> None:
        if not self.current_segments:
            self._log("Chưa có dữ liệu để tạo giọng đọc.")
            return
        try:
            self._log("Bắt đầu tạo TTS tiếng Việt cho từng đoạn...")
            self.current_segments = synthesize_segments(
                self.current_segments,
                self.output_folder.text().strip(),
                self.tts_voice.currentText(),
                int(self.tts_speed.text() or 0),
                int(self.tts_volume.text() or 0),
                int(self.tts_pitch.text() or 0),
                speaker_profiles=self.speaker_profiles,
            )
            self._log(f"Đã tạo {len(self.current_segments)} file TTS trong thư mục temp/tts_segments.")
        except Exception:
            self._log("TTS tiếng Việt bằng edge-tts cần kết nối Internet.")

    def _sync_and_export_dubbed(self) -> None:
        if not self.current_segments or not self.selected_video_path:
            self._log("Cần có video và dữ liệu TTS.")
            return
        try:
            self._log("Đang đồng bộ từng đoạn TTS theo mốc thời gian gốc...")
            timeline, plan = sync_tts_to_timeline(self.selected_video_path, self.current_segments, self.output_folder.text().strip(), max_speed=min(1.5, float(self.max_speech_speed.text() or 1.25)), safety_gap=float(self.safety_gap.text() or 0.15), logger=self._log)
            out = str(Path(self.output_folder.text().strip()) / "final_dubbed_video.mp4")
            export_final_dubbed_video(self.selected_video_path, timeline, out, self.orig_audio_mode.currentText(), int(self.orig_audio_pct.text() or 70), int(self.vi_voice_pct.text() or 100), logger=self._log)
            self._log(f"Hoàn tất đồng bộ và lồng tiếng: {out} | số đoạn: {len(plan)}")
        except Exception as e:
            self._log(f"LỖI đồng bộ/lồng tiếng: {e}")

    def _test_voice(self) -> None:
        try:
            out = synthesize_preview(self.tts_test_text.text().strip() or "Xin chào", self.output_folder.text().strip(), self.tts_voice.currentText(), int(self.tts_speed.text() or 0), int(self.tts_volume.text() or 0), int(self.tts_pitch.text() or 0))
            self._log(f"Đã lưu thử giọng: {out}")
        except Exception:
            self._log("TTS tiếng Việt bằng edge-tts cần kết nối Internet.")

    def _render_subtitles(self) -> None:
        if not self.current_segments or not self.selected_video_path:
            self._log("Cần có video và dữ liệu dịch.")
            return
        out = Path(self.output_folder.text().strip()); out.mkdir(parents=True, exist_ok=True)
        style = SubtitleStyle(font_name=self.font_name.text().strip() or "Arial", font_size=int(self.font_size.text() or 36), text_color=self.text_color.text().strip() or "#000000", outline_color=self.outline_color.text().strip() or "#000000", background_color=self.bg_color.text().strip() or "#000000", background_opacity=int(float(self.bg_opacity.text() or 40)), position=self.sub_pos.currentText(), bold=(self.bold.currentText()=="on"))
        cover = CoverBoxSettings(enabled=(self.cover_enabled.currentText() == "on"), color=self.cover_color.text().strip() or "yellow")
        srt = generate_srt(self.current_segments, str(out / "translated.srt"))
        ass = generate_ass(self.current_segments, str(out / "translated.ass"), style)
        self._log(f"Đã tạo: {srt}")
        self._log(f"Đã tạo: {ass}")
        if self.export.currentText() == "MP4 video":
            final = str(out / "final_subtitled_video.mp4")
            render_subtitled_video(self.selected_video_path, ass, final, cover, logger=self._log)
            self._log(f"Đã kết xuất video phụ đề: {final}")

    def _refresh_speaker_panel(self) -> None:
        self.speaker_table.setRowCount(0)
        for spk, prof in sorted(self.speaker_profiles.items()):
            r = self.speaker_table.rowCount(); self.speaker_table.insertRow(r)
            self.speaker_table.setItem(r, 0, QTableWidgetItem(spk))
            self.speaker_table.setItem(r, 1, QTableWidgetItem(str(prof.get("voice", "vi-VN-HoaiMyNeural"))))
            self.speaker_table.setItem(r, 2, QTableWidgetItem(str(prof.get("speed", 0))))
            self.speaker_table.setItem(r, 3, QTableWidgetItem(str(prof.get("volume", 0))))

    def _apply_speaker_profiles(self) -> None:
        profiles = {}
        for r in range(self.speaker_table.rowCount()):
            spk = self.speaker_table.item(r, 0).text() if self.speaker_table.item(r, 0) else f"SPEAKER_{r:02d}"
            profiles[spk] = {
                "voice": self.speaker_table.item(r, 1).text() if self.speaker_table.item(r, 1) else "vi-VN-HoaiMyNeural",
                "speed": int(self.speaker_table.item(r, 2).text() if self.speaker_table.item(r, 2) else "0"),
                "volume": int(self.speaker_table.item(r, 3).text() if self.speaker_table.item(r, 3) else "0"),
            }
        self.speaker_profiles = build_speaker_profiles(self.current_segments, profiles)
        for r in range(min(self.table.rowCount(), len(self.current_segments))):
            i = self.table.item(r, 2)
            if i:
                self.current_segments[r]["speaker"] = i.text()
        self._refresh_speaker_panel()
        self._log("Đã áp dụng chỉnh sửa người nói.")

    def _export_project_json(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Xuất Project JSON", str(Path(self.output_folder.text().strip()) / "project.json"), "JSON (*.json)")
        if not p:
            return
        Path(p).write_text(json.dumps({"segments": self.current_segments, "speaker_profiles": self.speaker_profiles, "video": self.selected_video_path, "output": self.output_folder.text().strip()}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"Đã xuất project: {p}")

    def _import_project_json(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Nhập Project JSON", "", "JSON (*.json)")
        if not p:
            return
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        self.current_segments = ensure_speakers(d.get("segments", []))
        self.speaker_profiles = build_speaker_profiles(self.current_segments, d.get("speaker_profiles", {}))
        self.selected_video_path = d.get("video", self.selected_video_path)
        self.output_folder.setText(d.get("output", self.output_folder.text()))
        self._fill_table(self.current_segments)
        self._refresh_speaker_panel()
        self._log(f"Đã nhập project: {p}")

    def _auto_diarize_info(self) -> None:
        self.lbl_diar.setText(auto_diarize_placeholder(self.selected_video_path).get("message", "Tùy chọn"))
        self._log(self.lbl_diar.text())

    def _check_environment(self) -> None:
        lines = [f"ffmpeg: {'OK' if shutil.which('ffmpeg') else 'THIẾU'}", f"faster-whisper: {'OK' if importlib.util.find_spec('faster_whisper') else 'THIẾU'}", f"transformers: {'OK' if importlib.util.find_spec('transformers') else 'THIẾU'}", f"edge-tts: {'OK' if importlib.util.find_spec('edge_tts') else 'THIẾU'}"]
        self._log(" | ".join(lines))

    def _export_debug_report(self) -> None:
        rp, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo debug", str(Path(self.output_folder.text().strip()) / "debug_report.txt"), "Text (*.txt)")
        if not rp:
            return
        ff = "unknown"
        try:
            ff = subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]
        except Exception:
            pass
        tail = Path(self.log_file).read_text(encoding="utf-8", errors="ignore").splitlines()[-100:] if Path(self.log_file).exists() else []
        Path(rp).write_text("\n".join([f"Phiên bản app: {__version__}", f"Windows: {platform.platform()}", f"Python: {platform.python_version()}", f"ffmpeg: {ff}", f"Model đã chọn: whisper={self.model_size.currentText()}, compute={self.compute_type.currentText()}, source={self.source_lang.currentText()}", "", "100 dòng log gần nhất:", *tail]), encoding="utf-8")
        self._log(f"Đã xuất báo cáo debug: {rp}")

    def _fill_table(self, segments: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for seg in segments:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(f"{seg['start']:.2f}"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{seg['end']:.2f}"))
            self.table.setItem(r, 2, QTableWidgetItem(seg.get("speaker", "SPEAKER_00")))
            self.table.setItem(r, 3, QTableWidgetItem(seg.get("source_text", "")))
            self.table.setItem(r, 4, QTableWidgetItem(seg.get("vi_subtitle_text") or seg.get("vi_dubbing_text") or ""))

    def _load_stylesheet(self) -> None:
        qss = Path(__file__).resolve().parents[2] / "ui" / "style.qss"
        if qss.exists():
            self.setStyleSheet(qss.read_text(encoding="utf-8"))

    def _log(self, msg: str) -> None:
        self.log.appendPlainText(msg)
        self.logger.info(msg)


def run_app() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
