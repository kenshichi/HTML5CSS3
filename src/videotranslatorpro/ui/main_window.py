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

from src.core.audio_extract import FFmpegNotFoundError, extract_audio
from src.core.diarization import build_speaker_profiles, ensure_speakers
from src.videotranslatorpro.core.transcribe import transcribe_audio, save_transcript_json
from src.videotranslatorpro.core.subtitle_detection import detect_source_subtitles
from src.videotranslatorpro.core.tts import VOICE_FEMALE, VOICE_MALE, list_voices, synthesize_text, synthesize_segments
from src.videotranslatorpro.core.translate import translate_segments_to_vietnamese, save_transcript_vi
from src.videotranslatorpro.core.subtitle import generate_srt, generate_ass, save_subtitle_settings
from src.videotranslatorpro.core.render_video import render_subtitled_video, save_render_settings
from src.videotranslatorpro.core.sync_audio import sync_tts_to_timeline, export_dubbed_video
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
        self.state = {"has_transcript": False, "has_translation": False, "has_subtitle": False, "has_subtitled_video": False, "has_tts": False, "has_dubbed_video": False}
        self.lang_map = {"auto": "en", "zh": "zh", "en": "en", "ja": "ja", "ko": "ko"}
        self._setup_logger()
        self._build_ui()
        self._bind_events()
        self._load_tts_voices()
        self._update_button_states()

    def _setup_logger(self) -> None:
        d = Path("output") / "logs"
        d.mkdir(parents=True, exist_ok=True)
        self.log_file = d / "app.log"
        logging.basicConfig(filename=str(self.log_file), level=logging.INFO)
        self.logger = logging.getLogger("VideoTranslatorPro")

    def _refresh_step_list(self) -> None:
        colors = {"Chưa làm":"⚪", "Đang xử lý":"🔵", "Hoàn tất":"🟢", "Lỗi":"🔴"}
        self.steps.clear()
        for i, name in enumerate(self.step_names, start=1):
            st = self.step_status[i-1]
            self.steps.addItem(f"{colors.get(st, '⚪')} Bước {i}: {name}")

    def _set_step_status(self, idx: int, status: str) -> None:
        if 0 <= idx < len(self.step_status):
            self.step_status[idx] = status
            self._refresh_step_list()

    def _build_ui(self) -> None:
        root = QWidget()
        h = QHBoxLayout(root)
        self.steps = QListWidget()
        self.step_names = ["Chọn video", "Cấu hình đầu ra", "Phân tích tự động", "Kiểm tra & chỉnh sửa", "Preview", "Xuất file"]
        self.step_status = ["Chưa làm"] * len(self.step_names)
        self._refresh_step_list()
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
        self.subtitle_strategy = QComboBox()
        self.subtitle_strategy.addItems([
            "Tự động, khuyên dùng",
            "Thêm phụ đề Việt ở dưới",
            "Thêm phụ đề Việt ở trên",
            "Đặt phụ đề Việt trên phụ đề gốc",
            "Đặt phụ đề Việt dưới phụ đề gốc",
            "Che phụ đề gốc và thay bằng phụ đề Việt",
            "Chỉ tạo file phụ đề rời",
        ])
        self.mode = QComboBox(); self.mode.addItems(["Chế độ nhanh", "Chế độ nâng cao"])
        self.btn_auto = QPushButton("Phân tích tự động")
        self.btn_auto.setMinimumHeight(42)
        g.addWidget(QLabel("Mục tiêu đầu ra"), 0, 0)
        g.addWidget(self.goal, 0, 1)
        g.addWidget(QLabel("Chiến lược phụ đề"), 1, 0)
        g.addWidget(self.subtitle_strategy, 1, 1, 1, 4)
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
        self.translation_mode = QComboBox(); self.translation_mode.addItems(["Dịch đầy đủ cho phụ đề", "Dịch ngắn cho lồng tiếng", "Dịch tự nhiên", "Giữ sát nghĩa"])
        self.experimental_translate = QCheckBox("Dịch thử nghiệm")
        self.default_voice = QComboBox(); self.default_voice.addItems([VOICE_FEMALE, VOICE_MALE])
        self.tts_speed = QSpinBox(); self.tts_speed.setRange(-50, 50); self.tts_speed.setValue(0)
        self.tts_pitch = QSpinBox(); self.tts_pitch.setRange(-50, 50); self.tts_pitch.setValue(0)
        self.tts_volume = QSpinBox(); self.tts_volume.setRange(-50, 50); self.tts_volume.setValue(0)
        self.test_tts_text = QLineEdit("Xin chào, đây là bản nghe thử tiếng Việt.")
        self.sync_mode = QComboBox(); self.sync_mode.addItems(["Tự động cân thời lượng", "Ưu tiên khớp thời gian gốc", "Ưu tiên nghe tự nhiên"])
        self.audio_mode = QComboBox(); self.audio_mode.addItems(["Giữ âm thanh gốc", "Giảm âm lượng âm thanh gốc", "Tắt âm thanh gốc"])
        self.safety_gap = QDoubleSpinBox(); self.safety_gap.setRange(0.05, 0.50); self.safety_gap.setSingleStep(0.01); self.safety_gap.setValue(0.15)
        self.source_audio_volume = QSpinBox(); self.source_audio_volume.setRange(0, 100); self.source_audio_volume.setValue(100)
        self.vi_audio_volume = QSpinBox(); self.vi_audio_volume.setRange(0, 200); self.vi_audio_volume.setValue(100)
        self.tts_engine = QComboBox(); self.tts_engine.addItems(["Edge TTS", "Piper (slot dự phòng)", "Engine khác (tương lai)"])
        self.safety_mode = QComboBox(); self.safety_mode.addItems(["Tự động cân thời lượng", "Ưu tiên khớp thời gian gốc", "Ưu tiên nghe tự nhiên"])
        gf.addRow("Ngôn ngữ nguồn", self.source_lang)
        gf.addRow("Mô hình Whisper", self.model)
        gf.addRow("Kiểu tính toán", self.compute)
        gf.addRow("Giọng đọc mặc định", self.default_voice)
        gf.addRow("Tốc độ đọc", self.tts_speed)
        gf.addRow("Cao độ", self.tts_pitch)
        gf.addRow("Âm lượng giọng Việt", self.tts_volume)
        gf.addRow("Văn bản nghe thử", self.test_tts_text)
        gf.addRow("Chế độ đồng bộ", self.sync_mode)
        gf.addRow("Khoảng an toàn (giây)", self.safety_gap)
        gf.addRow("Chế độ âm thanh gốc", self.audio_mode)
        gf.addRow("Âm lượng âm thanh gốc", self.source_audio_volume)
        gf.addRow("Âm lượng giọng Việt", self.vi_audio_volume)
        gf.addRow("Chế độ dịch", self.translation_mode)
        gf.addRow("Tuỳ chọn dịch", self.experimental_translate)
        gf.addRow("TTS engine", self.tts_engine)
        gf.addRow("Chế độ cân thời gian", self.safety_mode)
        self.sub_font = QFontComboBox(); self.sub_font.setCurrentFont(QFont("Arial"))
        self.sub_size = QSpinBox(); self.sub_size.setRange(18, 72); self.sub_size.setValue(44)
        self.sub_bold = QCheckBox("In đậm")
        self.sub_position = QComboBox(); self.sub_position.addItems(["Dưới giữa", "Trên giữa", "Giữa màn hình"])
        self.sub_margin = QSpinBox(); self.sub_margin.setRange(10, 200); self.sub_margin.setValue(40)
        self.cover_enabled = QCheckBox("Bật che phụ đề cũ")
        self.cover_color = QLineEdit("#000000")
        self.cover_height = QSpinBox(); self.cover_height.setRange(20, 400); self.cover_height.setValue(120)
        self.cover_position = QComboBox(); self.cover_position.addItems(["Phía dưới", "Phía trên", "Tuỳ chỉnh Y"])
        gf.addRow("Font chữ", self.sub_font)
        gf.addRow("Cỡ chữ", self.sub_size)
        gf.addRow("Kiểu chữ", self.sub_bold)
        gf.addRow("Vị trí phụ đề", self.sub_position)
        gf.addRow("Khoảng cách mép", self.sub_margin)
        gf.addRow("Che phụ đề cũ", self.cover_enabled)
        gf.addRow("Màu vùng che", self.cover_color)
        gf.addRow("Chiều cao vùng che", self.cover_height)
        gf.addRow("Vị trí vùng che", self.cover_position)
        v.addWidget(QLabel("Thư mục đầu ra")); v.addWidget(self.out_dir); v.addWidget(self.btn_out)
        v.addWidget(self.quick_hint); v.addWidget(self.adv_group); v.addStretch(1)
        return w

    def _page_analysis(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        self.summary = QTextEdit(); self.summary.setReadOnly(True)
        self.subtitle_preview = QLabel("Chưa có preview phụ đề")
        self.detect_card = QLabel("Kết quả phát hiện phụ đề gốc:\n- Có phụ đề gốc: chưa kiểm tra\n- Vị trí: chưa rõ\n- Độ tin cậy: 0.00\n- Gợi ý: Tự động, khuyên dùng\n- Ảnh mẫu: chưa có")
        self.btn_detect_sub = QPushButton("Kiểm tra phụ đề gốc")
        self.subtitle_preview.setMinimumHeight(120)
        self.summary.setPlaceholderText("Kết quả phân tích tự động sẽ hiển thị tại đây...")
        v.addWidget(QLabel("Tóm tắt phân tích"))
        v.addWidget(self.summary)
        v.addWidget(QLabel("Preview phụ đề"))
        v.addWidget(self.subtitle_preview)
        v.addWidget(self.detect_card)
        v.addWidget(self.btn_detect_sub)
        return w

    def _page_review(self) -> QWidget:
        w = QWidget(); h = QHBoxLayout(w)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Người nói", "Văn bản gốc", "Bản dịch tiếng Việt", "Trạng thái dịch", "Trạng thái TTS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        h.addWidget(self.table, 2)
        self.btn_translate_all = QPushButton("Dịch sang tiếng Việt")
        self.btn_translate_selected = QPushButton("Dịch lại đoạn đã chọn")
        self.btn_apply_edit = QPushButton("Áp dụng chỉnh sửa")

        side = QGroupBox("Quản lý người nói")
        v = QVBoxLayout(side)
        self.speaker_table = QTableWidget(0, 10)
        self.speaker_table.setHorizontalHeaderLabels(["Người nói", "Tên hiển thị", "Số câu", "Tổng thời lượng", "Xuất hiện đầu tiên", "Giọng", "Tốc độ", "Cao độ", "Âm lượng", "Nghe thử"])
        self.speaker_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.speaker_table.horizontalHeader().setStretchLastSection(True)
        self.btn_auto_voice = QPushButton("Tự gán giọng thông minh")
        self.btn_apply_all = QPushButton("Áp dụng cho tất cả câu")
        self.btn_rename = QPushButton("Đổi tên người nói")
        self.btn_preview_default = QPushButton("Nghe thử giọng")
        self.btn_generate_tts = QPushButton("Tạo giọng đọc")
        v.addWidget(self.speaker_table); v.addWidget(self.btn_auto_voice); v.addWidget(self.btn_apply_all); v.addWidget(self.btn_rename); v.addWidget(self.btn_preview_default); v.addWidget(self.btn_generate_tts)
        left_btns = QVBoxLayout(); left_btns.addWidget(self.btn_translate_all); left_btns.addWidget(self.btn_translate_selected); left_btns.addWidget(self.btn_apply_edit); left_btns.addStretch(1)
        h.addLayout(left_btns)
        h.addWidget(side, 1)
        return w

    def _page_export(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        self.btn_export_sub = QPushButton("Tạo phụ đề SRT/ASS")
        self.btn_render_video = QPushButton("Kết xuất video phụ đề")
        self.btn_export_dub = QPushButton("Xuất lồng tiếng (final_dubbed_video.mp4)")
        self.btn_report = QPushButton("Xuất báo cáo lỗi")
        self.progress = QProgressBar(); self.progress.setValue(0)
        for b in [self.btn_export_sub, self.btn_render_video, self.btn_export_dub, self.btn_report]:
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
        self.btn_detect_sub.clicked.connect(self._detect_source_subtitle)
        self.btn_report.clicked.connect(self._export_debug)
        self.btn_export_sub.clicked.connect(self._export_subtitles)
        self.btn_render_video.clicked.connect(self._render_subtitled_video)
        self.btn_translate_all.clicked.connect(self._translate_all)
        self.btn_translate_selected.clicked.connect(self._translate_selected)
        self.btn_apply_edit.clicked.connect(self._apply_manual_edits)
        self.btn_auto_voice.clicked.connect(self._auto_assign_speaker_voices)
        self.btn_preview_default.clicked.connect(self._preview_default_voice)
        self.btn_apply_all.clicked.connect(self._apply_speaker_table_to_segments)
        self.table.cellChanged.connect(self._on_table_cell_changed)
        self.btn_generate_tts.clicked.connect(self._generate_tts_segments)
        self.btn_export_dub.clicked.connect(self._sync_and_export_dubbed_video)
        self.goal.currentTextChanged.connect(self._update_button_states)

    def _load_tts_voices(self) -> None:
        voices = list_voices()
        self.default_voice.clear()
        for v in voices:
            self.default_voice.addItem(v.get("display", v.get("id")), v.get("id"))

    def _generate_tts_segments(self) -> None:
        if not self.state.get("has_translation"):
            self._log("[WARNING] Chưa có bản dịch tiếng Việt. Vui lòng bấm 'Dịch sang tiếng Việt' trước khi tạo giọng đọc.")
            return
        if not self.current_segments:
            self._log("[WARNING] Chưa có đoạn hội thoại để tạo giọng.")
            return
        try:
            self._apply_speaker_table_to_segments()
            total = len(self.current_segments)
            for i in range(total):
                self._log(f"[INFO] Đang tạo giọng đọc đoạn {i+1}/{total}...")
            manifest = synthesize_segments(self.current_segments, self.speaker_profiles, self.out_dir.text().strip())
            self._fill_table(self.current_segments)
            mpath = Path(manifest.get("manifest_path", ""))
            if not mpath.exists():
                self._log("[ERROR] Không tạo được tệp manifest TTS.")
                return
            self.state["has_tts"] = True
            self._update_button_states()
            self._log("[OK] Đã tạo giọng đọc.")
            self._log(f"[OK] Tệp manifest: {manifest.get('manifest_path', '')}")
            self._save_project_json()
            self._update_button_states()
        except Exception:
            self._log("[ERROR] Lỗi khi tạo giọng đọc.")
            self._log("[WARNING] Edge TTS cần kết nối internet.")

    def _on_table_cell_changed(self, row: int, col: int) -> None:
        if row >= len(self.current_segments):
            return
        if col == 2:
            it = self.table.item(row, col)
            if it:
                self.current_segments[row]["speaker"] = it.text().strip() or "SPEAKER_01"
                self.speaker_profiles = build_speaker_profiles(self.current_segments, self.speaker_profiles)
                self._fill_speaker_panel()
                self._log("[OK] Đã cập nhật danh sách người nói.")

    def _save_project_json(self) -> str:
        out = Path(self.out_dir.text().strip())
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "transcript": self.current_segments,
            "speaker_profiles": self.speaker_profiles,
            "subtitle_settings": self._subtitle_style_settings() if hasattr(self, "sub_font") else {},
            "dubbing_settings": {
                "sync_mode": self.sync_mode.currentText(),
                "safety_gap": self.safety_gap.value(),
                "audio_mode": self.audio_mode.currentText(),
                "source_audio_volume": self.source_audio_volume.value(),
                "vi_audio_volume": self.vi_audio_volume.value(),
            },
        }
        fp = out / "project_state.json"
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log("[OK] Đã lưu cấu hình người nói.")
        return str(fp)

    def _sync_table_edits_to_segments(self) -> None:
        for r in range(min(self.table.rowCount(), len(self.current_segments))):
            spk = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else "SPEAKER_01"
            src = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            vi = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
            self.current_segments[r]["speaker"] = spk or "SPEAKER_01"
            self.current_segments[r]["source_text"] = src
            self.current_segments[r]["vi_subtitle_text"] = vi
            self.current_segments[r]["vi_dubbing_text"] = vi.replace("\n", " ")

    def _update_button_states(self) -> None:
        has_transcript = bool(self.state.get("has_transcript"))
        has_translation = bool(self.state.get("has_translation"))
        has_subtitle = bool(self.state.get("has_subtitle"))
        has_tts = bool(self.state.get("has_tts"))

        self.btn_translate_all.setEnabled(has_transcript)
        self.btn_translate_selected.setEnabled(has_transcript)
        self.btn_export_sub.setEnabled(has_translation)
        self.btn_generate_tts.setEnabled(has_translation)
        self.btn_export_dub.setEnabled(has_tts)
        self.btn_render_video.setEnabled(has_subtitle)

        self.btn_translate_all.setToolTip("Cần transcript trước khi dịch." if not has_transcript else "")
        self.btn_translate_selected.setToolTip("Cần transcript trước khi dịch." if not has_transcript else "")
        self.btn_export_sub.setToolTip("Cần bản dịch tiếng Việt trước khi tạo phụ đề." if not has_translation else "")
        self.btn_generate_tts.setToolTip("Cần bản dịch tiếng Việt trước khi tạo giọng đọc." if not has_translation else "")
        self.btn_export_dub.setToolTip("Cần tạo giọng đọc (TTS) trước khi đồng bộ & lồng tiếng." if not has_tts else "")
        self.btn_render_video.setToolTip("Cần tạo phụ đề ASS trước khi kết xuất video phụ đề." if not has_subtitle else "")

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
            self._set_step_status(2, "Lỗi")
            self._log("[WARNING] Vui lòng chọn video trước khi phân tích.")
            return
        try:
            self._set_step_status(2, "Đang xử lý")
            self._log("[INFO] Đang chuẩn bị nhận diện lời nói...")
            out_audio = Path("temp") / "audio" / "input_16k_mono.wav"
            out_audio.parent.mkdir(parents=True, exist_ok=True)
            stream_idx = self._selected_stream_index() if hasattr(self, "_selected_stream_index") else None
            if not out_audio.exists():
                self._log("[INFO] Đang trích âm thanh...")
                r = extract_audio(self.selected_video_path, str(out_audio), stream_idx)
                self.logger.info("ffmpeg cmd: %s", r.command)
                if not r.success:
                    self._set_step_status(2, "Lỗi")
                    self._log("[ERROR] Không thể trích âm thanh.")
                    return
                self._log("[OK] Đã trích âm thanh thành công.")
            self._log("[INFO] Lần đầu sử dụng mô hình này có thể cần tải dữ liệu, vui lòng chờ.")
            self._log("[INFO] Đang tải mô hình Whisper...")
            res = transcribe_audio(str(out_audio), language=self.source_lang.currentText(), model_size=self.model.currentText(), compute_type=self.compute.currentText())
            self._log("[INFO] Đang cập nhật bảng lời thoại...")
            self.current_segments = ensure_speakers(res.segments)
            self._fill_table(self.current_segments)
            self.speaker_profiles = build_speaker_profiles(self.current_segments, self.speaker_profiles)
            self._fill_speaker_panel()
            save_transcript_json(self.out_dir.text().strip(), getattr(self, "video_meta", {}), self.audio_source.currentText() if hasattr(self, "audio_source") else "auto", self.source_lang.currentText(), self.model.currentText(), self.compute.currentText(), self.current_segments)
            if self.current_segments:
                self._log(f"[OK] Đã nhận diện {len(self.current_segments)} đoạn lời thoại.")
            else:
                self._log("[WARNING] Không nhận diện được lời thoại nào.")
            self.summary.setPlainText(f"Số đoạn lời thoại: {len(self.current_segments)}\nNgôn ngữ nguồn phát hiện: {res.detected_language}\nTrạng thái nhận diện: Hoàn tất\nSố người nói dự kiến: 1")
            self._detect_source_subtitle()
            self.state["has_transcript"] = True
            self._set_step_status(2, "Hoàn tất")
            self._set_step_status(3, "Đang xử lý")
            self.steps.setCurrentRow(3)
            self._update_button_states()
        except FFmpegNotFoundError:
            self._set_step_status(2, "Lỗi")
            self._log("[ERROR] Không tìm thấy ffmpeg.")
        except Exception:
            self._set_step_status(2, "Lỗi")
            self._log("[ERROR] Lỗi khi nhận diện lời nói.")

    def _detect_source_subtitle(self) -> None:
        if not self.selected_video_path:
            self._log("[WARNING] Vui lòng chọn video trước khi kiểm tra phụ đề gốc.")
            return
        try:
            self._log("[INFO] Đang kiểm tra phụ đề gốc...")
            result = detect_source_subtitles(self.selected_video_path, self.out_dir.text().strip())
            has_sub = result.get("has_source_subtitle")
            pos = result.get("probable_position", "unknown")
            conf = float(result.get("confidence", 0.0))
            suggest = result.get("suggested_strategy", "Tự động, khuyên dùng")
            frames = result.get("sample_frames", [])
            if has_sub is True and pos == "bottom":
                self._log("[OK] Có thể video có phụ đề ở phía dưới.")
            elif has_sub is False:
                self._log("[OK] Không phát hiện phụ đề gốc.")
            elif conf < 0.45:
                self._log("[WARNING] Không chắc chắn, vui lòng kiểm tra thủ công.")
            self.detect_card.setText(
                "Kết quả phát hiện phụ đề gốc:\n"
                f"- Có phụ đề gốc: {has_sub}\n"
                f"- Vị trí phụ đề gốc: {pos}\n"
                f"- Độ tin cậy: {conf:.2f}\n"
                f"- Gợi ý hiển thị phụ đề Việt: {suggest}\n"
                f"- Đường dẫn ảnh mẫu: {', '.join(frames) if frames else 'không có'}"
            )
            if self.subtitle_strategy.currentText() == "Tự động, khuyên dùng":
                idx = self.subtitle_strategy.findText(suggest)
                if idx >= 0:
                    self.subtitle_strategy.setCurrentIndex(idx)
        except Exception:
            self._log("[ERROR] Lỗi khi kiểm tra phụ đề gốc.")

    def _fill_table(self, segs: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for s in segs:
            r = self.table.rowCount(); self.table.insertRow(r)
            vals = [f"{s['start']:.2f}", f"{s['end']:.2f}", s.get("speaker", "SPEAKER_01"), s.get("source_text", ""), s.get("vi_subtitle_text", ""), s.get("translation_status", "Chưa dịch"), s.get("tts_status", "Chưa tạo giọng")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 4:
                    it.setToolTip("Bạn có thể sửa bản dịch tiếng Việt trước khi tạo TTS/kết xuất phụ đề.")
                if c == 2:
                    it.setToolTip("Có thể nhập SPEAKER_01/SPEAKER_02/... hoặc nhãn tuỳ chỉnh")
                self.table.setItem(r, c, it)

    def _fill_speaker_panel(self) -> None:
        self.speaker_table.setRowCount(0)
        for spk, prof in sorted(self.speaker_profiles.items()):
            rows = [s for s in self.current_segments if s.get("speaker") == spk]
            dur = sum(float(s["end"]) - float(s["start"]) for s in rows)
            r = self.speaker_table.rowCount(); self.speaker_table.insertRow(r)
            first = min(float(s["start"]) for s in rows) if rows else 0.0
            display = prof.get("display_name", spk)
            vals = [spk, display, str(len(rows)), f"{dur:.1f}s", f"{first:.1f}s", prof.get("voice", VOICE_FEMALE), str(prof.get("speed", 0)), str(prof.get("pitch", 0)), str(prof.get("volume", 0)), "▶"]
            for c, v in enumerate(vals):
                self.speaker_table.setItem(r, c, QTableWidgetItem(v))


    def _auto_assign_speaker_voices(self) -> None:
        spks = sorted(self.speaker_profiles.keys())
        vi_voices = [VOICE_FEMALE, VOICE_MALE]
        if len(spks) == 1:
            self.speaker_profiles[spks[0]]["voice"] = self.default_voice.currentData() or VOICE_FEMALE
        elif len(spks) == 2:
            self.speaker_profiles[spks[0]]["voice"] = VOICE_FEMALE
            self.speaker_profiles[spks[1]]["voice"] = VOICE_MALE
        else:
            for i, spk in enumerate(spks):
                self.speaker_profiles[spk]["voice"] = vi_voices[i % len(vi_voices)]
                self.speaker_profiles[spk]["speed"] = (-3 if i % 2 else 2)
                self.speaker_profiles[spk]["pitch"] = (2 if i % 3 == 0 else -1)
        for spk in spks:
            self.speaker_profiles[spk].setdefault("speed", 0)
            self.speaker_profiles[spk].setdefault("pitch", 0)
            self.speaker_profiles[spk].setdefault("volume", 0)
            self.speaker_profiles[spk].setdefault("display_name", spk)
        self._fill_speaker_panel()
        self._log("[OK] Đã gán giọng mặc định cho người nói.")

    def _preview_default_voice(self) -> None:
        try:
            text = self.test_tts_text.text().strip() if hasattr(self, "test_tts_text") else "Xin chào, đây là giọng mặc định."
            out = str(Path(self.out_dir.text().strip()) / "tts_preview.mp3")
            voice_id = self.default_voice.currentData() or self.default_voice.currentText()
            synthesize_text(text, out, voice_id, self.tts_speed.value(), self.tts_pitch.value(), self.tts_volume.value())
            self._log(f"[OK] Đã tạo giọng đọc. File nghe thử: {out}")
        except Exception:
            self._log("[WARNING] Edge TTS cần kết nối internet.")

    def _apply_speaker_table_to_segments(self) -> None:
        # update profile overrides and apply to all segments by label
        for r in range(self.speaker_table.rowCount()):
            spk = self.speaker_table.item(r, 0).text() if self.speaker_table.item(r, 0) else f"SPEAKER_{r:02d}"
            display = self.speaker_table.item(r, 1).text() if self.speaker_table.item(r, 1) else spk
            voice = self.speaker_table.item(r, 5).text() if self.speaker_table.item(r, 5) else VOICE_FEMALE
            speed = int(self.speaker_table.item(r, 6).text() if self.speaker_table.item(r, 6) else "0")
            pitch = int(self.speaker_table.item(r, 7).text() if self.speaker_table.item(r, 7) else "0")
            volume = int(self.speaker_table.item(r, 8).text() if self.speaker_table.item(r, 8) else "0")
            self.speaker_profiles.setdefault(spk, {})
            self.speaker_profiles[spk].update({"display_name": display, "voice": voice, "speed": speed, "pitch": pitch, "volume": volume})
        self._log("Đã áp dụng cấu hình giọng cho tất cả câu theo từng người nói.")


    def _apply_manual_edits(self) -> None:
        for r in range(min(self.table.rowCount(), len(self.current_segments))):
            vi_item = self.table.item(r, 4)
            if vi_item:
                self.current_segments[r]["vi_subtitle_text"] = vi_item.text()
                self.current_segments[r]["vi_dubbing_text"] = vi_item.text().replace("\n", " ")
                self.current_segments[r]["manual_edited"] = True
        self._log("[OK] Đã áp dụng chỉnh sửa thủ công bản dịch.")

    def _translate_all(self) -> None:
        if not self.state.get("has_transcript"):
            self._log("[WARNING] Chưa có transcript để dịch.")
            return
        self._log("[INFO] Đang tải mô hình dịch...")
        total = len([x for x in self.current_segments if not x.get("manual_edited", False)])
        for i in range(total):
            self._log(f"[INFO] Đang dịch đoạn {i+1}/{total}...")
        rows, warning = translate_segments_to_vietnamese(self.current_segments, self.lang_map.get(self.source_lang.currentText(), "auto"), self.translation_mode.currentText(), experimental_mode=self.experimental_translate.isChecked())
        self.current_segments = rows
        self._fill_table(self.current_segments)
        self.state["has_translation"] = True
        if warning:
            self._log(warning)
        if not any((r.get("vi_subtitle_text") or "").strip() for r in rows):
            self.state["has_translation"] = False
            self._update_button_states()
            self._log("[WARNING] Chưa có mô hình dịch phù hợp.")
            return
        self._log(f"[OK] Đã dịch {len(rows)} đoạn lời thoại.")
        fp = save_transcript_vi(self.out_dir.text().strip(), self.lang_map.get(self.source_lang.currentText(), "auto"), self.translation_mode.currentText(), self.current_segments, rows)
        self._log(f"[OK] Đã lưu bản dịch: {fp}")
        self._update_button_states()

    def _translate_selected(self) -> None:
        sel = sorted({i.row() for i in self.table.selectedIndexes()})
        if not sel:
            self._log("[WARNING] Vui lòng chọn đoạn cần dịch lại.")
            return
        temp = [self.current_segments[i] for i in sel]
        for x in temp:
            x["manual_edited"] = False
        rows, warning = translate_segments_to_vietnamese(temp, self.lang_map.get(self.source_lang.currentText(), "auto"), self.translation_mode.currentText(), experimental_mode=self.experimental_translate.isChecked())
        for k, idx in enumerate(sel):
            self.current_segments[idx].update(rows[k])
        self._fill_table(self.current_segments)
        if warning:
            self._log(warning)
        self._log("[OK] Đã dịch lại các đoạn đã chọn.")


    def _sync_and_export_dubbed_video(self) -> None:
        if not self.state.get("has_tts"):
            self._log("[WARNING] Vui lòng tạo giọng đọc trước khi đồng bộ.")
            return
        if not self.selected_video_path or not self.current_segments or not self.state.get("has_transcript"):
            self._log("[WARNING] Thiếu dữ liệu video/transcript để lồng tiếng.")
            return
        try:
            self._log("[INFO] Đang đồng bộ giọng đọc...")
            report = sync_tts_to_timeline(
                self.current_segments,
                self.selected_video_path,
                self.out_dir.text().strip(),
                safety_gap=float(self.safety_gap.value()),
                mode=self.sync_mode.currentText(),
            )
            for x in report.get("segments", []):
                if x.get("status") == "speedup":
                    self._log(f"[INFO] Đoạn {x.get('index')} quá dài, đang tăng tốc...")
                if x.get("status") == "trim":
                    self._log(f"[WARNING] Đoạn {x.get('index')} vẫn quá dài, đã cắt để tránh đè tiếng.")
            out_video = export_dubbed_video(
                self.selected_video_path,
                report.get("timeline_audio"),
                str(Path(self.out_dir.text().strip()) / "final_dubbed_video.mp4"),
                self.audio_mode.currentText(),
                int(self.source_audio_volume.value()),
                int(self.vi_audio_volume.value()),
            )
            if not Path(out_video).exists() or not Path(report.get("timeline_audio", "")).exists():
                self._log("[ERROR] Đồng bộ/lồng tiếng chưa tạo đủ tệp đầu ra.")
                return
            self.state["has_dubbed_video"] = True
            self._log(f"[OK] Đã tạo video lồng tiếng.\n- {report.get('timeline_audio')}\n- {out_video}\n- {Path(self.out_dir.text().strip()) / 'sync_report.json'}")
            self._save_project_json()
        except Exception:
            self._log("[ERROR] Lỗi khi tạo giọng đọc.")
            self._log("[WARNING] Edge TTS cần kết nối internet.")

    def _subtitle_style_settings(self) -> Dict[str, Any]:
        if self.mode.currentText() == "Chế độ nhanh":
            return {
                "font": "Arial", "font_size": 44, "text_color": "&H00FFFFFF", "outline_color": "&H00000000",
                "outline_width": 2, "back_color": "&H64000000", "bold": False, "position": 2, "margin_v": 40
            }
        pos_map = {"Dưới giữa": 2, "Trên giữa": 8, "Giữa màn hình": 5}
        return {
            "font": self.sub_font.currentFont().family(),
            "font_size": self.sub_size.value(),
            "text_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline_width": 2,
            "back_color": "&H64000000",
            "bold": self.sub_bold.isChecked(),
            "position": pos_map.get(self.sub_position.currentText(), 2),
            "margin_v": self.sub_margin.value(),
            "cover_enabled": self.cover_enabled.isChecked(),
            "cover_color": self.cover_color.text().strip(),
            "cover_height": self.cover_height.value(),
            "cover_position": self.cover_position.currentText(),
        }

    def _export_subtitles(self) -> None:
        if not self.state.get("has_translation"):
            self._log("[WARNING] Chưa có bản dịch tiếng Việt để tạo phụ đề.")
            return
        try:
            self._apply_manual_edits()
            out_dir = Path(self.out_dir.text().strip())
            out_dir.mkdir(parents=True, exist_ok=True)
            self._log("[INFO] Đang tạo phụ đề SRT...")
            srt_path, warn1 = generate_srt(self.current_segments, str(out_dir / "translated_vi.srt"))
            self._log("[INFO] Đang tạo phụ đề ASS...")
            style = self._subtitle_style_settings()
            ass_path, warn2 = generate_ass(self.current_segments, str(out_dir / "translated_vi.ass"), style)
            settings_path = save_subtitle_settings(str(out_dir), style)
            if not Path(srt_path).exists() or not Path(ass_path).exists():
                self._log("[ERROR] Tạo phụ đề thất bại do thiếu tệp đầu ra.")
                return
            self.state["has_subtitle"] = True
            self._set_step_status(4, "Hoàn tất")
            self._set_step_status(5, "Đang xử lý")
            self.subtitle_preview.setText("Đây là ví dụ phụ đề tiếng Việt.")
            self._log(f"[OK] Đã tạo phụ đề thành công.\n- {srt_path}\n- {ass_path}\n- {settings_path}")
            if warn1:
                self._log(warn1)
            if warn2:
                self._log(warn2)
        except Exception:
            self._log("[ERROR] Lỗi khi tạo phụ đề.")


    def _render_subtitled_video(self) -> None:
        if not self.selected_video_path:
            self._log("[WARNING] Vui lòng chọn video trước khi kết xuất.")
            return
        if not self.state.get("has_subtitle"):
            self._log("[WARNING] Chưa có phụ đề. Vui lòng tạo SRT/ASS trước.")
            return
        try:
            out_dir = Path(self.out_dir.text().strip())
            ass_path = out_dir / "translated_vi.ass"
            if not ass_path.exists():
                self._log("[WARNING] Không tìm thấy file ASS để kết xuất.")
                return
            self._log("[INFO] Đang kết xuất video có phụ đề...")
            strategy = self.subtitle_strategy.currentText()
            cover = {
                "cover_color": self.cover_color.text().strip() or "yellow",
                "opacity": 0.75,
                "height_pct": self.cover_height.value() / 1000.0 if self.cover_height.value() > 1 else 0.14,
                "y_pct": 0.78 if self.cover_position.currentText() == "Phía dưới" else (0.12 if self.cover_position.currentText() == "Phía trên" else 0.50),
                "padding": 8,
            }
            if strategy == "Che phụ đề gốc và thay bằng phụ đề Việt":
                self._log("[INFO] Đang che phụ đề gốc...")
            out_video, settings = render_subtitled_video(
                self.selected_video_path, str(ass_path), str(out_dir / "final_subtitled_video.mp4"), strategy, cover
            )
            if settings.get("skipped"):
                self._log("[INFO] Đang ở chế độ chỉ xuất file phụ đề rời, bỏ qua kết xuất video.")
                return
            self.logger.info("ffmpeg cmd render: %s", " ".join(settings.get("ffmpeg_command", [])))
            settings_path = save_render_settings(str(out_dir), settings)
            if not Path(out_video).exists():
                self._log("[ERROR] Kết xuất chưa tạo được tệp video.")
                return
            self.state["has_subtitled_video"] = True
            self._set_step_status(5, "Hoàn tất")
            self._log(f"[OK] Đã xuất video phụ đề thành công.\n- {out_video}\n- {settings_path}")
        except Exception as e:
            self._log("[ERROR] Lỗi khi kết xuất video.")
            self.logger.exception("render error: %s", e)

    def _export_debug(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo lỗi", str(Path(self.out_dir.text().strip()) / "debug_report.txt"), "Text (*.txt)")
        if not p:
            return
        try:
            self._sync_table_edits_to_segments()
        except Exception:
            self._log("[WARNING] Không thể đồng bộ chỉnh sửa bảng trước khi xuất báo cáo.")
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
        from datetime import datetime
        self.log.appendPlainText("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg)
        self.logger.info(msg)


def run_app() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
