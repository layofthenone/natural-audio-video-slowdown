from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from PySide6 import QtCore


@dataclass
class AppSettings:
    """Serializable application settings."""

    input_dir: str = ""
    output_dir: str = ""
    concurrent_jobs: int = 0  # 0 means auto (CPU-1)
    overwrite: bool = False
    preset: str = "Balanced"  # Visually lossless | Balanced | Smaller file size
    video_encoder: str = "libx264"  # libx264 | h264_nvenc | h264_qsv | h264_videotoolbox
    video_preset: str = "slow"
    video_crf: int = 18
    audio_codec: str = "aac"
    audio_bitrate: int = 192
    copy_subtitles: bool = True
    preview_enabled: bool = False
    preview_seconds: int = 20
    gpu_enabled: bool = False
    ffmpeg_path: str = ""  # optional explicit path to ffmpeg executable
    ffprobe_path: str = ""  # optional explicit path to ffprobe executable


class SettingsStore:
    """Stores settings in the platform's app data location as JSON."""

    def __init__(self, app_name: str = "VideoSlowdown") -> None:
        base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppLocalDataLocation)
        self._dir = Path(base) / app_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "settings.json"

    def load(self) -> AppSettings:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                return AppSettings(**data)
            except Exception:
                pass
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        payload = asdict(settings)
        self._file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
