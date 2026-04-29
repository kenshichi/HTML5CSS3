from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import *
import importlib.util
import logging
import platform
import shutil
import subprocess
from typing import Dict, List, Any

from src.core.audio_extract import FFmpegNotFoundError
from src.core.transcribe import transcribe_video
from src.core.translate import translate_segments_to_vietnamese
from src.core.subtitle import SubtitleStyle, CoverBoxSettings, generate_srt, generate_ass, render_subtitled_video
from src.core.tts import VOICE_FEMALE, VOICE_MALE, synthesize_segments, synthesize_preview
from src.core.sync_audio import sync_tts_to_timeline, export_final_dubbed_video
from src.core.diarization import ensure_speakers, build_speaker_profiles, auto_diarize_placeholder
from src.videotranslatorpro import __version__




class FirstRunSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("First-Run Setup Check")
        self.resize(700, 420)
        v=QVBoxLayout(self)
        info=QLabel("Checks dependencies and tools. Models are NOT bundled in EXE and should be in models/.")
        self.text=QPlainTextEdit(); self.text.setReadOnly(True)
        btn=QPushButton("Run Checks")
        btn.clicked.connect(self.run_checks)
        close_btn=QPushButton("Continue")
        close_btn.clicked.connect(self.accept)
        row=QHBoxLayout(); row.addWidget(btn); row.addWidget(close_btn); row.addStretch(1)
        v.addWidget(info); v.addWidget(self.text); v.addLayout(row)

    def run_checks(self):
        lines=[]
        for m in ["PySide6","faster_whisper","transformers","edge_tts"]:
            ok = importlib.util.find_spec(m) is not None
            lines.append(f"[{ 'OK' if ok else 'MISSING' }] Python dependency: {m}")
        ff=shutil.which("ffmpeg") is not None
        lines.append(f"[{ 'OK' if ff else 'MISSING' }] ffmpeg in PATH")
        fw=(Path("models")/"faster-whisper").exists()
        lines.append(f"[{ 'OK' if fw else 'MISSING' }] faster-whisper model folder: models/faster-whisper")
        nllb=(Path("models")/"nllb-200-distilled-600M").exists()
        lines.append(f"[{ 'OK' if nllb else 'MISSING' }] NLLB model folder: models/nllb-200-distilled-600M")
        lines.append("edge-tts may require internet access at runtime.")
        self.text.setPlainText("\n".join(lines))

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoTranslatorPro")
        self.resize(1500, 920)
        self.selected_video_path = ""
        self.detected_language = None
        self.current_segments = []
        self.speaker_profiles = {}
        self.debug_mode = True
        self._setup_logger()
        self._build_ui(); self._load_stylesheet(); self._bind_events()
        self._show_first_run_setup()


    def _setup_logger(self) -> None:
        log_dir=Path("output")/"logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file=log_dir/"app.log"
        logging.basicConfig(filename=str(self.log_file), level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        self.logger=logging.getLogger("VideoTranslatorPro")
        self.logger.info("App started. Debug mode=%s", self.debug_mode)

    def _show_first_run_setup(self) -> None:
        dlg=FirstRunSetupDialog(self)
        dlg.run_checks()
        dlg.exec()

    def _build_ui(self) -> None:
        root = QWidget(); layout = QVBoxLayout(root)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_sidebar()); split.addWidget(self._build_main()); split.setSizes([260, 1240])
        layout.addWidget(split); self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        side=QFrame(); side.setObjectName("Sidebar"); v=QVBoxLayout(side)
        v.addWidget(QLabel("🎬 VideoTranslatorPro"))
        self.steps=QListWidget(); self.steps.setObjectName("StepsList")
        for s in ["1. Import Video","2. Transcribe","3. Translate","4. Subtitles","5. Voice Dubbing","6. Speaker Voices","7. Export"]: self.steps.addItem(s)
        v.addWidget(self.steps); v.addStretch(1); return side

    def _build_main(self) -> QWidget:
        w=QWidget(); v=QVBoxLayout(w)
        self.video_name=QLineEdit("No video selected"); self.video_name.setReadOnly(True)
        self.video_duration=QLineEdit("--:--:--"); self.video_duration.setReadOnly(True)
        self.video_resolution=QLineEdit("---- x ----"); self.video_resolution.setReadOnly(True)
        self.output_folder=QLineEdit(str(Path.cwd()/"output")); self.output_folder.setReadOnly(True)
        self.btn_video=QPushButton("📁 Select Video"); self.btn_output=QPushButton("🗂 Select Output Folder")
        top=QFrame(); top.setObjectName("TopBar"); g=QGridLayout(top)
        g.addWidget(QLabel("Video"),0,0); g.addWidget(self.video_name,0,1); g.addWidget(self.btn_video,0,2)
        g.addWidget(QLabel("Duration"),1,0); g.addWidget(self.video_duration,1,1); g.addWidget(QLabel("Resolution"),1,2); g.addWidget(self.video_resolution,1,3)
        g.addWidget(QLabel("Output Folder"),2,0); g.addWidget(self.output_folder,2,1,1,3); g.addWidget(self.btn_output,2,4)
        v.addWidget(top)

        self.source_lang=QComboBox(); self.source_lang.addItems(["auto","zh","en","ja","ko"])
        self.translation_style=QComboBox(); self.translation_style.addItems(["Full translation for subtitles","Short translation for dubbing"])
        self.model_size=QComboBox(); self.model_size.addItems(["tiny","base","small","medium"])
        self.compute_type=QComboBox(); self.compute_type.addItems(["int8","float16","float32"])
        self.export=QComboBox(); self.export.addItems(["MP4 video","SRT only","ASS only","Audio only"])
        self.font_file=QLineEdit(""); self.font_name=QLineEdit("Arial"); self.font_size=QLineEdit("36")
        self.text_color=QLineEdit("#000000"); self.outline_color=QLineEdit("#000000"); self.bg_color=QLineEdit("#000000"); self.bg_opacity=QLineEdit("40")
        self.bold=QComboBox(); self.bold.addItems(["off","on"]); self.sub_pos=QComboBox(); self.sub_pos.addItems(["top","middle","bottom"]); self.margin_v=QLineEdit("40")
        self.cover_enabled=QComboBox(); self.cover_enabled.addItems(["off","on"]); self.cover_color=QLineEdit("yellow"); self.cover_h=QLineEdit("0.18"); self.cover_y=QLineEdit("0.78")
        self.tts_voice=QComboBox(); self.tts_voice.addItems([VOICE_FEMALE, VOICE_MALE])
        self.tts_speed=QLineEdit("0")
        self.tts_volume=QLineEdit("0")
        self.tts_pitch=QLineEdit("0")
        self.tts_test_text=QLineEdit("Xin chào, đây là bản thử giọng tiếng Việt.")
        self.max_speech_speed=QLineEdit("1.25")
        self.safety_gap=QLineEdit("0.15")
        self.orig_audio_mode=QComboBox(); self.orig_audio_mode.addItems(["Keep original audio","Lower original audio volume","Mute original audio"])
        self.orig_audio_pct=QLineEdit("70")
        self.vi_voice_pct=QLineEdit("100")

        formbox=QGroupBox("Settings"); form=QFormLayout(formbox)
        for label, widget in [
            ("Source",self.source_lang),("Translation style",self.translation_style),("Whisper model",self.model_size),("Compute",self.compute_type),("Export",self.export),
            ("Font file",self.font_file),("Font name",self.font_name),("Font size",self.font_size),("Text color",self.text_color),("Outline color",self.outline_color),
            ("Background color",self.bg_color),("Background opacity",self.bg_opacity),("Bold",self.bold),("Subtitle position",self.sub_pos),("Margin vertical",self.margin_v),
            ("Cover old subtitle",self.cover_enabled),("Cover box color",self.cover_color),("Cover box height %",self.cover_h),("Cover box Y",self.cover_y),
            ("Default TTS voice",self.tts_voice),("TTS speed",self.tts_speed),("TTS volume",self.tts_volume),("TTS pitch",self.tts_pitch),("Test voice text",self.tts_test_text),
            ("Max speech speed (<=1.50)",self.max_speech_speed),("Safety gap (sec)",self.safety_gap),("Original audio mode",self.orig_audio_mode),("Original audio volume %",self.orig_audio_pct),("Vietnamese voice volume %",self.vi_voice_pct),]: form.addRow(label,widget)

        self.btn_start=QPushButton("▶ Start Transcribe"); self.btn_translate=QPushButton("🌐 Translate"); self.btn_tts=QPushButton("🔊 Generate TTS"); self.btn_sync_dub=QPushButton("🎚 Sync+Dub"); self.btn_test_voice=QPushButton("🧪 Test Voice"); self.btn_render=QPushButton("🎞 Render"); self.btn_check_env=QPushButton("🧩 Check Environment"); self.btn_export_debug=QPushButton("📤 Export Debug Report"); self.btn_cancel=QPushButton("⏹ Cancel")
        self.progress=QProgressBar(); self.progress.setValue(0)
        row=QHBoxLayout(); [row.addWidget(b) for b in [self.btn_start,self.btn_translate,self.btn_tts,self.btn_sync_dub,self.btn_test_voice,self.btn_render,self.btn_check_env,self.btn_export_debug,self.btn_cancel]]; row.addStretch(1)
        v.addWidget(formbox); v.addLayout(row); v.addWidget(self.progress)

        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["start","end","speaker","source text","Vietnamese text"]); v.addWidget(self.table,2)
        self.speaker_panel=QGroupBox("Speaker Voice Panel")
        spv=QVBoxLayout(self.speaker_panel)
        self.speaker_table=QTableWidget(0,4)
        self.speaker_table.setHorizontalHeaderLabels(["Speaker","Voice","Speed","Volume"])
        self.btn_apply_speaker=QPushButton("Apply speaker edits")
        self.btn_auto_diar=QPushButton("Auto diarization (optional)")
        self.lbl_diar=QLabel("Auto speaker detection is optional and may require model setup.")
        spv.addWidget(self.speaker_table); spv.addWidget(self.btn_apply_speaker); spv.addWidget(self.btn_auto_diar); spv.addWidget(self.lbl_diar)
        v.addWidget(self.speaker_panel)
        io=QHBoxLayout(); self.btn_export_project=QPushButton("Export Project JSON"); self.btn_import_project=QPushButton("Import Project JSON"); io.addWidget(self.btn_export_project); io.addWidget(self.btn_import_project); io.addStretch(1); v.addLayout(io)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); v.addWidget(self.log,1)
        return w

    def _bind_events(self) -> None:
        self.btn_video.clicked.connect(self._pick_video); self.btn_output.clicked.connect(self._pick_output)
        self.btn_start.clicked.connect(self._run_transcription); self.btn_translate.clicked.connect(self._run_translation); self.btn_tts.clicked.connect(self._run_tts); self.btn_sync_dub.clicked.connect(self._sync_and_export_dubbed); self.btn_test_voice.clicked.connect(self._test_voice); self.btn_render.clicked.connect(self._render_subtitles); self.btn_check_env.clicked.connect(self._check_environment); self.btn_export_debug.clicked.connect(self._export_debug_report); self.btn_apply_speaker.clicked.connect(self._apply_speaker_profiles); self.btn_export_project.clicked.connect(self._export_project_json); self.btn_import_project.clicked.connect(self._import_project_json); self.btn_auto_diar.clicked.connect(self._auto_diarize_info)

    def _pick_video(self) -> None:
        p,_=QFileDialog.getOpenFileName(self,"Select Video","","Video Files (*.mp4 *.mkv *.avi *.mov)")
        if p: self.selected_video_path=p; self.video_name.setText(Path(p).name); self._log(f"Video selected: {p}")

    def _pick_output(self) -> None:
        p=QFileDialog.getExistingDirectory(self,"Select Output Folder")
        if p: self.output_folder.setText(p); self._log(f"Output folder selected: {p}")

    def _run_transcription(self) -> None:
        if not self.selected_video_path: self._log("Please select a video first."); return
        try:
            segs,lang=transcribe_video(self.selected_video_path,self.output_folder.text().strip(),self.source_lang.currentText(),self.model_size.currentText(),self.compute_type.currentText())
            self.current_segments=ensure_speakers(segs); self.detected_language=lang; self.speaker_profiles=build_speaker_profiles(self.current_segments, self.speaker_profiles); self._fill_table(self.current_segments); self._refresh_speaker_panel(); self._log(f"Transcription done: {len(segs)}")
        except FFmpegNotFoundError as e: self._log(f"ERROR: {e}")
        except Exception as e: self._log(f"ERROR transcription: {e}")

    def _run_translation(self) -> None:
        if not self.current_segments: self._log("No transcript available."); return
        mode="full" if self.translation_style.currentIndex()==0 else "short"
        segs,w=translate_segments_to_vietnamese(self.current_segments,self.output_folder.text().strip(),self.source_lang.currentText(),mode,self.detected_language)
        self.current_segments=ensure_speakers(segs); self.speaker_profiles=build_speaker_profiles(self.current_segments, self.speaker_profiles); self._fill_table(self.current_segments); self._refresh_speaker_panel(); self._log(w or "Translation done.")

    def _run_tts(self) -> None:
        if not self.current_segments:
            self._log("No translated segments available for dubbing.")
            return
        try:
            voice=self.tts_voice.currentText()
            speed=int(self.tts_speed.text() or 0)
            volume=int(self.tts_volume.text() or 0)
            pitch=int(self.tts_pitch.text() or 0)
            self.current_segments = synthesize_segments(self.current_segments, self.output_folder.text().strip(), voice, speed, volume, pitch, speaker_profiles=self.speaker_profiles)
            self._log(f"Generated TTS for {len(self.current_segments)} segments in temp/tts_segments")
        except Exception:
            self._log("Vietnamese TTS requires internet when using edge-tts.")

    def _sync_and_export_dubbed(self) -> None:
        if not self.current_segments or not self.selected_video_path:
            self._log("Need video + TTS segments.")
            return
        try:
            max_speed=min(1.5, float(self.max_speech_speed.text() or 1.25))
            safety=float(self.safety_gap.text() or 0.15)
            timeline, plan = sync_tts_to_timeline(
                self.selected_video_path,
                self.current_segments,
                self.output_folder.text().strip(),
                max_speed=max_speed,
                safety_gap=safety,
                logger=self._log,
            )
            out=str(Path(self.output_folder.text().strip())/"final_dubbed_video.mp4")
            export_final_dubbed_video(
                self.selected_video_path,
                timeline,
                out,
                self.orig_audio_mode.currentText(),
                int(self.orig_audio_pct.text() or 70),
                int(self.vi_voice_pct.text() or 100),
                logger=self._log,
            )
            self._log(f"Dubbed video exported: {out}")
            self._log(f"Sync plan segments: {len(plan)}")
        except Exception as e:
            self._log(f"ERROR sync/dub: {e}")


    def _test_voice(self) -> None:
        try:
            out = synthesize_preview(
                self.tts_test_text.text().strip() or "Xin chào",
                self.output_folder.text().strip(),
                self.tts_voice.currentText(),
                int(self.tts_speed.text() or 0),
                int(self.tts_volume.text() or 0),
                int(self.tts_pitch.text() or 0),
            )
            self._log(f"Voice preview saved: {out}")
        except Exception:
            self._log("Vietnamese TTS requires internet when using edge-tts.")


    def _render_subtitles(self) -> None:
        if not self.current_segments or not self.selected_video_path: self._log("Need video + segments."); return
        out=Path(self.output_folder.text().strip()); out.mkdir(parents=True, exist_ok=True)
        style=SubtitleStyle(
            font_file=self.font_file.text().strip(), font_name=self.font_name.text().strip() or "Arial", font_size=int(self.font_size.text() or 36),
            text_color=self.text_color.text().strip() or "#000000", outline_color=self.outline_color.text().strip() or "#000000",
            background_color=self.bg_color.text().strip() or "#000000", background_opacity=int(float(self.bg_opacity.text() or 40)),
            bold=(self.bold.currentText()=="on"), position=self.sub_pos.currentText(), margin_vertical=int(self.margin_v.text() or 40),
        )
        cover=CoverBoxSettings(enabled=(self.cover_enabled.currentText()=="on"), color=self.cover_color.text().strip() or "yellow", height_percent=float(self.cover_h.text() or 0.18), y_percent=float(self.cover_y.text() or 0.78))
        srt=generate_srt(self.current_segments, str(out/"translated.srt")); ass=generate_ass(self.current_segments, str(out/"translated.ass"), style)
        self._log(f"Generated: {srt}"); self._log(f"Generated: {ass}")
        if self.export.currentText()=="MP4 video":
            final=str(out/"final_subtitled_video.mp4")
            render_subtitled_video(self.selected_video_path, ass, final, cover, logger=self._log)
            self._log(f"Generated: {final}")

    def _refresh_speaker_panel(self) -> None:
        self.speaker_table.setRowCount(0)
        for spk, prof in sorted(self.speaker_profiles.items()):
            r=self.speaker_table.rowCount(); self.speaker_table.insertRow(r)
            self.speaker_table.setItem(r,0,QTableWidgetItem(spk))
            self.speaker_table.setItem(r,1,QTableWidgetItem(str(prof.get("voice","vi-VN-HoaiMyNeural"))))
            self.speaker_table.setItem(r,2,QTableWidgetItem(str(prof.get("speed",0))))
            self.speaker_table.setItem(r,3,QTableWidgetItem(str(prof.get("volume",0))))

    def _apply_speaker_profiles(self) -> None:
        profiles={}
        for r in range(self.speaker_table.rowCount()):
            spk=self.speaker_table.item(r,0).text() if self.speaker_table.item(r,0) else f"SPEAKER_{r:02d}"
            voice=self.speaker_table.item(r,1).text() if self.speaker_table.item(r,1) else "vi-VN-HoaiMyNeural"
            speed=int((self.speaker_table.item(r,2).text() if self.speaker_table.item(r,2) else "0"))
            volume=int((self.speaker_table.item(r,3).text() if self.speaker_table.item(r,3) else "0"))
            profiles[spk]={"voice":voice,"speed":speed,"volume":volume}
        self.speaker_profiles=profiles
        for r in range(self.table.rowCount()):
            item=self.table.item(r,2)
            if item:
                self.current_segments[r]["speaker"]=item.text()
        self.speaker_profiles=build_speaker_profiles(self.current_segments, self.speaker_profiles)
        self._refresh_speaker_panel()
        self._log("Speaker profiles applied.")

    def _export_project_json(self) -> None:
        import json
        p,_=QFileDialog.getSaveFileName(self,"Export Project JSON",str(Path(self.output_folder.text().strip())/"project.json"),"JSON (*.json)")
        if not p: return
        data={"segments":self.current_segments,"speaker_profiles":self.speaker_profiles,"video":self.selected_video_path,"output":self.output_folder.text().strip()}
        Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        self._log(f"Project exported: {p}")

    def _import_project_json(self) -> None:
        import json
        p,_=QFileDialog.getOpenFileName(self,"Import Project JSON","","JSON (*.json)")
        if not p: return
        data=json.loads(Path(p).read_text(encoding="utf-8"))
        self.current_segments=ensure_speakers(data.get("segments",[]))
        self.speaker_profiles=build_speaker_profiles(self.current_segments, data.get("speaker_profiles",{}))
        self.selected_video_path=data.get("video",self.selected_video_path)
        self.output_folder.setText(data.get("output",self.output_folder.text()))
        self._fill_table(self.current_segments); self._refresh_speaker_panel()
        self._log(f"Project imported: {p}")

    def _auto_diarize_info(self) -> None:
        info=auto_diarize_placeholder(self.selected_video_path)
        self.lbl_diar.setText(info.get("message","Auto speaker detection is optional."))
        self._log(self.lbl_diar.text())

    def _check_environment(self) -> None:
        lines=[]
        ff=shutil.which("ffmpeg") is not None
        lines.append(f"ffmpeg: {'OK' if ff else 'MISSING'}")
        cuda=False
        try:
            import torch
            cuda=torch.cuda.is_available()
        except Exception:
            cuda=False
        lines.append(f"GPU/CUDA: {'AVAILABLE' if cuda else 'NOT AVAILABLE'}")
        for m,name in [("faster_whisper","faster-whisper"),("transformers","transformers"),("edge_tts","edge-tts")]:
            ok=importlib.util.find_spec(m) is not None
            lines.append(f"{name} import: {'OK' if ok else 'MISSING'}")
        out=Path(self.output_folder.text().strip())
        try:
            out.mkdir(parents=True, exist_ok=True)
            test=out/".__write_test"
            test.write_text("ok",encoding="utf-8"); test.unlink()
            writable=True
        except Exception:
            writable=False
        lines.append(f"Output folder writable: {'YES' if writable else 'NO'}")
        msg="\n".join(lines)
        self._log(msg)

    def _export_debug_report(self) -> None:
        report_path,_=QFileDialog.getSaveFileName(self,"Export Debug Report",str(Path(self.output_folder.text().strip())/"debug_report.txt"),"Text (*.txt)")
        if not report_path:
            return
        ffver="unknown"
        try:
            ffver=subprocess.check_output(["ffmpeg","-version"], text=True).splitlines()[0]
        except Exception:
            pass
        log_tail=[]
        if hasattr(self,'log_file') and Path(self.log_file).exists():
            log_tail=Path(self.log_file).read_text(encoding="utf-8",errors="ignore").splitlines()[-100:]
        content=[
            f"App version: {__version__}",
            f"Windows version: {platform.platform()}",
            f"Python version: {platform.python_version()}",
            f"ffmpeg version: {ffver}",
            f"Selected model settings: whisper={self.model_size.currentText()}, compute={self.compute_type.currentText()}, source_lang={self.source_lang.currentText()}",
            "",
            "Last 100 log lines:",
            *log_tail,
        ]
        Path(report_path).write_text("\n".join(content), encoding="utf-8")
        self._log(f"Debug report exported: {report_path}")


    def _fill_table(self, segments: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for seg in segments:
            r=self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r,0,QTableWidgetItem(f"{seg['start']:.2f}")); self.table.setItem(r,1,QTableWidgetItem(f"{seg['end']:.2f}"))
            self.table.setItem(r,2,QTableWidgetItem(seg.get("speaker","SPEAKER_00"))); self.table.setItem(r,3,QTableWidgetItem(seg.get("source_text","")))
            self.table.setItem(r,4,QTableWidgetItem(seg.get("vi_subtitle_text") or seg.get("vi_dubbing_text") or ""))

    def _load_stylesheet(self) -> None:
        qss=Path(__file__).resolve().parents[2]/"ui"/"style.qss"
        if qss.exists(): self.setStyleSheet(qss.read_text(encoding="utf-8"))

    def _log(self, msg: str) -> None:
        self.log.appendPlainText(msg)
        if hasattr(self, "logger"):
            self.logger.info(msg)


def run_app() -> None:
    app = QApplication(sys.argv); w = MainWindow(); w.show(); sys.exit(app.exec())
