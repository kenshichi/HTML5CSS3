from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
from pathlib import Path


class TTSManager:
    def __init__(self):
        self.engines = ["edge_tts", "piper", "coqui", "gtts"]

    def _has_module(self, name: str) -> bool:
        return importlib.util.find_spec(name) is not None

    async def _edge_async(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0):
        import edge_tts
        rate = f"{max(-50, min(50, speed)):+d}%"
        pitch_s = f"{max(-100, min(100, pitch)):+d}Hz"
        vol = f"{max(-50, min(50, volume)):+d}%"
        await edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch_s, volume=vol).save(output_path)

    def _synthesize_edge(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0):
        if not self._has_module("edge_tts"):
            raise RuntimeError("edge_tts_not_installed")
        asyncio.run(self._edge_async(text, voice, output_path, speed, pitch, volume))

    def _synthesize_piper(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0):
        piper_bin = shutil.which("piper")
        if not piper_bin:
            raise RuntimeError("piper_not_installed")
        model_dir = Path("models") / "piper" / "vi"
        model = next(model_dir.glob("*.onnx"), None) if model_dir.exists() else None
        if model is None:
            raise RuntimeError("piper_model_not_found")
        out_wav = str(Path(output_path).with_suffix(".wav"))
        cmd = [piper_bin, "-m", str(model), "-f", out_wav]
        subprocess.run(cmd, input=text, text=True, capture_output=True, check=True)
        if Path(out_wav).suffix.lower() != Path(output_path).suffix.lower():
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("ffmpeg_not_found_for_piper_convert")
            subprocess.run([ffmpeg, "-y", "-i", out_wav, output_path], capture_output=True, check=True)

    def _synthesize_coqui(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0):
        if not self._has_module("TTS"):
            raise RuntimeError("coqui_not_installed")
        from TTS.api import TTS
        tts = TTS(model_name="tts_models/vi/vivos/vits", progress_bar=False, gpu=False)
        tts.tts_to_file(text=text, file_path=output_path)

    def _synthesize_gtts(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0):
        if not self._has_module("gtts"):
            raise RuntimeError("gtts_not_installed")
        from gtts import gTTS
        gTTS(text=text, lang="vi").save(output_path)

    def synthesize(self, text: str, voice: str, output_path: str, speed: int = 0, pitch: int = 0, volume: int = 0, preferred_engine: str | None = None):
        if not text.strip():
            raise ValueError("empty_text")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        order = [preferred_engine] + self.engines if preferred_engine else list(self.engines)
        order = [x for i, x in enumerate(order) if x and x not in order[:i]]
        last_err = None
        for engine in order:
            try:
                if engine == "edge_tts":
                    self._synthesize_edge(text, voice if voice.startswith("vi-VN-") else "vi-VN-HoaiMyNeural", output_path, speed, pitch, volume)
                elif engine == "piper":
                    self._synthesize_piper(text, voice, output_path, speed, pitch, volume)
                elif engine == "coqui":
                    self._synthesize_coqui(text, voice, output_path, speed, pitch, volume)
                elif engine == "gtts":
                    self._synthesize_gtts(text, voice, output_path, speed, pitch, volume)
                else:
                    continue
                return {"success": True, "engine": engine, "output_path": output_path}
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"all_tts_engines_failed: {last_err}")
