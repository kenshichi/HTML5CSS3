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
from src.core.diarization import build_speaker_profiles, ensure_speakers
from src.core.transcribe import transcribe_video
from src.core.subtitle_detect import detect_burned_subtitle, suggest_vietnamese_placement
from src.core.tts import VOICE_FEMALE, VOICE_MALE, synthesize_preview
from src.videotranslatorpro import __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoTranslatorPro")
        self.resize(1500, 920)
        self.setMinimumSize(1200, 720)
        self.setFont(QFont("Segoe UI", 10))

        self.selected_video_path = ""
        self.current_segments: List[Dict[str, Any]] = []
        self.speaker_profiles: Dict[str, Dict[str, Any]] = {}
        self._setup_logger()
        self._build_ui()
        self._bind_events()

    def _setup_logger(self) -> None:
        d = Path("output") / "logs"
        d.mkdir(parents=True, exist_ok=True)
        self.log_file = d / "app.log"
        logging.basicConfig(filename=str(self.log_file), level=logging.INFO)
        self.logger = logging.getLogger("VideoTranslatorPro")

    def _build_ui(self) -> None:
        root = QWidget()
        h = QHBoxLayout(root)
        self.steps = QListWidget()
        self.steps.addItems([
            "Bước 1: Chọn video",
            "Bước 2: Chọn mục tiêu đầu ra",
            "Bước 3: Phân tích tự động",
            "Bước 4: Xem lại lời thoại & người nói",
            "Bước 5: Xuất file",
        ])
        self.steps.setFixedWidth(280)
        h.addWidget(self.steps)

        right = QVBoxLayout()
        right.addWidget(self._top_goal_bar())

        self.stack = QStackedWidget()
        self.page_video = self._page_video()
        self.page_goal = self._page_goal()
        self.page_analysis = self._page_analysis()
        self.page_review = self._page_review()
        self.page_export = self._page_export()
        for p in [self.page_video, self.page_goal, self.page_analysis, self.page_review, self.page_export]:
            self.stack.addWidget(p)
        right.addWidget(self.stack, 1)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(130)
        self.log.setPlaceholderText("Nhật ký xử lý...")
        right.addWidget(self.log)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Quay lại")
        self.btn_next = QPushButton("Tiếp theo ▶")
        nav.addStretch(1); nav.addWidget(self.btn_prev); nav.addWidget(self.btn_next)
        right.addLayout(nav)

        container = QWidget(); container.setLayout(right)
        h.addWidget(container, 1)
        self.setCentralWidget(root)
        self.steps.setCurrentRow(0)

    def _top_goal_bar(self) -> QWidget:
        f = QFrame(); g = QGridLayout(f)
        self.goal = QComboBox()
        self.goal.addItems([
            "Chỉ tạo phụ đề tiếng Việt",
            "Chỉ lồng tiếng tiếng Việt",
            "Phụ đề + lồng tiếng tiếng Việt",
            "Chỉ xuất transcript / SRT",
        ])
        self.mode = QComboBox(); self.mode.addItems(["Chế độ nhanh", "Chế độ nâng cao"])
        self.btn_auto = QPushButton("Phân tích tự động")
        self.btn_auto.setMinimumHeight(42)
        g.addWidget(QLabel("Mục tiêu đầu ra"), 0, 0)
        g.addWidget(self.goal, 0, 1)
        g.addWidget(QLabel("Chế độ"), 0, 2)
        g.addWidget(self.mode, 0, 3)
        g.addWidget(self.btn_auto, 0, 4)
        return f

    def _page_video(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        self.file_name = QLineEdit("Chưa chọn video"); self.file_name.setReadOnly(True)
        self.file_duration = QLineEdit("--:--:--"); self.file_duration.setReadOnly(True)
        self.file_resolution = QLineEdit("---- x ----"); self.file_resolution.setReadOnly(True)
        self.input_path = QLineEdit("--"); self.input_path.setReadOnly(True)
        self.btn_video = QPushButton("Chọn video")
        f.addRow("Tên tệp", self.file_name)
        f.addRow("Thời lượng", self.file_duration)
        f.addRow("Độ phân giải", self.file_resolution)
        f.addRow("Đường dẫn", self.input_path)
        f.addRow("", self.btn_video)
        return w

    def _page_goal(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        self.out_dir = QLineEdit(str(Path.cwd() / "output")); self.out_dir.setReadOnly(True)
        self.btn_out = QPushButton("Chọn thư mục đầu ra")
        self.quick_hint = QLabel("Chế độ nhanh: Ứng dụng tự dùng cấu hình an toàn mặc định.")
        self.adv_group = QGroupBox("Cấu hình nâng cao")
        gf = QFormLayout(self.adv_group)
        self.source_lang = QComboBox(); self.source_lang.addItems(["auto", "zh", "en", "ja", "ko"])
        self.model = QComboBox(); self.model.addItems(["tiny", "base", "small", "medium"])
        self.compute = QComboBox(); self.compute.addItems(["int8", "float16", "float32"])
        self.default_voice = QComboBox(); self.default_voice.addItems([VOICE_FEMALE, VOICE_MALE])
        self.tts_engine = QComboBox(); self.tts_engine.addItems(["Edge TTS", "Piper (slot dự phòng)", "Engine khác (tương lai)"])
        self.safety_mode = QComboBox(); self.safety_mode.addItems(["Tự động cân thời lượng", "Ưu tiên khớp thời gian gốc", "Ưu tiên nghe tự nhiên"])
        gf.addRow("Ngôn ngữ nguồn", self.source_lang)
        gf.addRow("Mô hình Whisper", self.model)
        gf.addRow("Kiểu tính toán", self.compute)
        gf.addRow("Giọng mặc định", self.default_voice)
        gf.addRow("TTS engine", self.tts_engine)
        gf.addRow("Chế độ cân thời gian", self.safety_mode)
        v.addWidget(QLabel("Thư mục đầu ra")); v.addWidget(self.out_dir); v.addWidget(self.btn_out)
        v.addWidget(self.quick_hint); v.addWidget(self.adv_group); v.addStretch(1)
        return w

    def _page_analysis(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        self.summary = QTextEdit(); self.summary.setReadOnly(True)
        self.subtitle_preview = QLabel("Chưa có preview phụ đề")
        self.subtitle_preview.setMinimumHeight(120)
        self.summary.setPlaceholderText("Kết quả phân tích tự động sẽ hiển thị tại đây...")
        v.addWidget(QLabel("Tóm tắt phân tích"))
        v.addWidget(self.summary)
        v.addWidget(QLabel("Preview phụ đề"))
        v.addWidget(self.subtitle_preview)
        return w

    def _page_review(self) -> QWidget:
        w = QWidget(); h = QHBoxLayout(w)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Người nói", "Văn bản gốc", "Bản dịch tiếng Việt", "Trạng thái TTS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        h.addWidget(self.table, 2)

        side = QGroupBox("Quản lý người nói")
        v = QVBoxLayout(side)
        self.speaker_table = QTableWidget(0, 10)
        self.speaker_table.setHorizontalHeaderLabels(["Người nói", "Tên hiển thị", "Số câu", "Tổng thời lượng", "Giọng", "Tốc độ", "Cao độ", "Âm lượng", "Nghe thử", "Áp dụng"])
        self.speaker_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_auto_voice = QPushButton("Tự gán giọng thông minh")
        self.btn_apply_all = QPushButton("Áp dụng cho tất cả câu")
        self.btn_rename = QPushButton("Đổi tên người nói")
        self.btn_preview_default = QPushButton("Nghe thử giọng mặc định")
        v.addWidget(self.speaker_table); v.addWidget(self.btn_auto_voice); v.addWidget(self.btn_apply_all); v.addWidget(self.btn_rename); v.addWidget(self.btn_preview_default)
        h.addWidget(side, 1)
        return w

    def _page_export(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        self.btn_export_sub = QPushButton("Xuất phụ đề (SRT/ASS)")
        self.btn_export_dub = QPushButton("Xuất lồng tiếng (final_dubbed_video.mp4)")
        self.btn_report = QPushButton("Xuất báo cáo lỗi")
        self.progress = QProgressBar(); self.progress.setValue(0)
        for b in [self.btn_export_sub, self.btn_export_dub, self.btn_report]:
            b.setMinimumHeight(38); v.addWidget(b)
        v.addWidget(self.progress); v.addStretch(1)
        return w

    def _bind_events(self) -> None:
        self.steps.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.btn_prev.clicked.connect(lambda: self.steps.setCurrentRow(max(0, self.steps.currentRow()-1)))
        self.btn_next.clicked.connect(lambda: self.steps.setCurrentRow(min(self.steps.count()-1, self.steps.currentRow()+1)))
        self.mode.currentTextChanged.connect(self._on_mode_changed)
        self.btn_video.clicked.connect(self._pick_video)
        self.btn_out.clicked.connect(self._pick_output)
        self.btn_auto.clicked.connect(self._auto_analyze)
        self.btn_report.clicked.connect(self._export_debug)
        self.btn_auto_voice.clicked.connect(self._auto_assign_speaker_voices)
        self.btn_preview_default.clicked.connect(self._preview_default_voice)
        self.btn_apply_all.clicked.connect(self._apply_speaker_table_to_segments)

    def _on_mode_changed(self) -> None:
        adv = self.mode.currentText() == "Chế độ nâng cao"
        self.adv_group.setVisible(adv)

    def _pick_video(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Chọn video", "", "Video Files (*.mp4 *.mkv *.avi *.mov)")
        if not p:
            return
        self.selected_video_path = p
        self.file_name.setText(Path(p).name)
        self.input_path.setText(p)
        try:
            md = self._read_video_metadata(p)
            self.file_duration.setText(md["duration"])
            self.file_resolution.setText(md["resolution"])
            self._log("Đã chọn video và đọc metadata thành công.")
        except Exception as e:
            self._log(f"Cảnh báo: không đọc được metadata ({e})")

    def _read_video_metadata(self, video_path: str) -> Dict[str, str]:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ], text=True).strip().splitlines()
        width, height, dur = out[0], out[1], float(out[2])
        h, m, s = int(dur//3600), int((dur%3600)//60), int(dur%60)
        return {"duration": f"{h:02d}:{m:02d}:{s:02d}", "resolution": f"{width} x {height}"}

    def _pick_output(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra")
        if p:
            self.out_dir.setText(p)

    def _auto_analyze(self) -> None:
        if not self.selected_video_path:
            self._log("Vui lòng chọn video trước.")
            return
        self._log("Bắt đầu phân tích tự động...")
        try:
            segs, lang = transcribe_video(self.selected_video_path, self.out_dir.text().strip(), self.source_lang.currentText(), self.model.currentText(), self.compute.currentText())
            self.current_segments = ensure_speakers(segs)
            self.speaker_profiles = build_speaker_profiles(self.current_segments, self.speaker_profiles)
            self._fill_table(self.current_segments)
            self._fill_speaker_panel()
            sub_info = detect_burned_subtitle(self.selected_video_path, self.out_dir.text().strip())
            suggested = suggest_vietnamese_placement(sub_info["has_subtitle"], sub_info["likely_position"])
            if self.subtitle_strategy.currentText() == "Tự động":
                self.sub_pos.setCurrentText(suggested)
                if sub_info["has_subtitle"] and sub_info["likely_position"] == "bottom":
                    self.subtitle_strategy.setCurrentText("Giữ phụ đề gốc, thêm phụ đề Việt ở trên")
                elif sub_info["has_subtitle"] and sub_info["likely_position"] == "top":
                    self.subtitle_strategy.setCurrentText("Giữ phụ đề gốc, thêm phụ đề Việt ở dưới")
            self.summary.setPlainText(
                f"Ngôn ngữ nguồn: {lang}\n"
                f"Thời lượng video: {self.file_duration.text()}\n"
                f"Phát hiện phụ đề gốc: {'Có' if sub_info['has_subtitle'] else 'Không'}\n"
                f"Vị trí phụ đề gốc ước lượng: {sub_info['likely_position']}\n"
                f"Số người nói: {len(self.speaker_profiles)}\n"
                f"Chế độ phụ đề đề xuất: {self.subtitle_strategy.currentText()}\n"
                f"Giọng mặc định được đề xuất: {self.default_voice.currentText()}"
            )
            self.subtitle_preview.setText("Vùng phụ đề phát hiện: " + str(sub_info['region']) + "\nVị trí phụ đề Việt đề xuất: " + self.sub_pos.currentText() + "\nFrame mẫu:\n" + "\n".join(sub_info['sample_frames']))
            self.steps.setCurrentRow(3)
            self._log("Phân tích tự động hoàn tất. Mời xem lại bảng lời thoại.")
        except FFmpegNotFoundError as e:
            self._log(f"Lỗi ffmpeg: {e}")
        except Exception as e:
            self._log(f"Lỗi phân tích: {e}")


    def _sync_table_edits_to_segments(self) -> None:
        if not self.current_segments:
            return
        for r in range(min(self.table.rowCount(), len(self.current_segments))):
            src = self.table.item(r, 3).text() if self.table.item(r, 3) else self.current_segments[r].get("source_text", "")
            vi = self.table.item(r, 4).text() if self.table.item(r, 4) else self.current_segments[r].get("vi_subtitle_text", "")
            spk = self.table.item(r, 2).text() if self.table.item(r, 2) else self.current_segments[r].get("speaker", "SPEAKER_00")
            self.current_segments[r]["source_text"] = src
            self.current_segments[r]["vi_subtitle_text"] = vi
            self.current_segments[r]["vi_dubbing_text"] = vi.replace("\n", " ")
            self.current_segments[r]["speaker"] = spk

    def _fill_table(self, segs: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for s in segs:
            r = self.table.rowCount(); self.table.insertRow(r)
            vals = [f"{s['start']:.2f}", f"{s['end']:.2f}", s.get("speaker", "SPEAKER_00"), s.get("source_text", ""), s.get("vi_subtitle_text", ""), s.get("tts_status", "Chưa tạo")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 4:
                    it.setToolTip("Bạn có thể sửa bản dịch tiếng Việt trước khi tạo TTS/kết xuất phụ đề.")
                self.table.setItem(r, c, it)

    def _fill_speaker_panel(self) -> None:
        self.speaker_table.setRowCount(0)
        for spk, prof in sorted(self.speaker_profiles.items()):
            rows = [s for s in self.current_segments if s.get("speaker") == spk]
            dur = sum(float(s["end"]) - float(s["start"]) for s in rows)
            r = self.speaker_table.rowCount(); self.speaker_table.insertRow(r)
            first = min(float(s["start"]) for s in rows) if rows else 0.0
            display = prof.get("display_name", spk)
            vals = [spk, f"{display} (xuất hiện {first:.1f}s)", str(len(rows)), f"{dur:.1f}s", prof.get("voice", VOICE_FEMALE), str(prof.get("speed", 0)), str(prof.get("pitch", 0)), str(prof.get("volume", 0)), "▶", "Áp dụng"]
            for c, v in enumerate(vals):
                self.speaker_table.setItem(r, c, QTableWidgetItem(v))


    def _auto_assign_speaker_voices(self) -> None:
        voices = [VOICE_FEMALE, VOICE_MALE]
        for i, spk in enumerate(sorted(self.speaker_profiles.keys())):
            self.speaker_profiles[spk]["voice"] = voices[i % 2]
            self.speaker_profiles[spk].setdefault("speed", 0)
            self.speaker_profiles[spk].setdefault("pitch", 0)
            self.speaker_profiles[spk].setdefault("volume", 0)
            self.speaker_profiles[spk].setdefault("display_name", spk)
        self._fill_speaker_panel()
        self._log("Đã tự gán giọng thông minh theo thứ tự Nam/Nữ xen kẽ.")

    def _preview_default_voice(self) -> None:
        try:
            out = synthesize_preview("Xin chào, đây là giọng mặc định.", self.out_dir.text().strip(), self.default_voice.currentText(), 0, 0, 0)
            self._log(f"Đã tạo file nghe thử giọng mặc định: {out}")
        except Exception:
            self._log("Không thể nghe thử giọng. Edge TTS có thể cần Internet.")

    def _apply_speaker_table_to_segments(self) -> None:
        # update profile overrides and apply to all segments by label
        for r in range(self.speaker_table.rowCount()):
            spk = self.speaker_table.item(r, 0).text() if self.speaker_table.item(r, 0) else f"SPEAKER_{r:02d}"
            display = self.speaker_table.item(r, 1).text() if self.speaker_table.item(r, 1) else spk
            voice = self.speaker_table.item(r, 4).text() if self.speaker_table.item(r, 4) else VOICE_FEMALE
            speed = int(self.speaker_table.item(r, 5).text() if self.speaker_table.item(r, 5) else "0")
            pitch = int(self.speaker_table.item(r, 6).text() if self.speaker_table.item(r, 6) else "0")
            volume = int(self.speaker_table.item(r, 7).text() if self.speaker_table.item(r, 7) else "0")
            self.speaker_profiles.setdefault(spk, {})
            self.speaker_profiles[spk].update({"display_name": display, "voice": voice, "speed": speed, "pitch": pitch, "volume": volume})
        self._log("Đã áp dụng cấu hình giọng cho tất cả câu theo từng người nói.")

    def _export_debug(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo lỗi", str(Path(self.out_dir.text().strip()) / "debug_report.txt"), "Text (*.txt)")
        if not p:
            return
        self._sync_table_edits_to_segments()
        ff = "unknown"
        try:
            ff = subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]
        except Exception:
            pass
        content = [f"App: {__version__}", f"Windows: {platform.platform()}", f"Python: {platform.python_version()}", f"ffmpeg: {ff}", f"TTS engine: {self.tts_engine.currentText()}", f"Safety mode: {self.safety_mode.currentText()}"]
        Path(p).write_text("\n".join(content), encoding="utf-8")
        # export artifacts snapshot
        out = Path(self.out_dir.text().strip())
        out.mkdir(parents=True, exist_ok=True)
        (out / "speaker_mapping.json").write_text(json.dumps(self.speaker_profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "translated_transcript.json").write_text(json.dumps(self.current_segments, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"Đã xuất báo cáo lỗi: {p}")

    def _log(self, msg: str) -> None:
        self.log.appendPlainText(msg)
        self.logger.info(msg)


def run_app() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
