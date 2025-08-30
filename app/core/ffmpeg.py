from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ProbeResult:
    duration: float
    has_video: bool
    has_audio: bool
    sample_rate: Optional[int]
    channels: Optional[int]
    channel_layout: Optional[str]


def _normalize_exe(path: str | None, name: str) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if p.is_dir():
        cand = p / name
        return str(cand) if cand.exists() else None
    return str(p) if p.exists() else None


def which_ffmpeg() -> str:
    # 1) Respect environment override
    env = os.environ.get("FFMPEG_PATH")
    cand = _normalize_exe(env, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if cand:
        return cand
    # 2) PATH
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # 3) Common relative locations (next to executable or project)
    here = Path(sys.executable).parent
    for rel in [
        "ffmpeg", "ffmpeg/bin", "bin", "tools/ffmpeg", "vendor/ffmpeg/bin",
    ]:
        p = _normalize_exe(str(here / rel), "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if p:
            return p
    raise FileNotFoundError("ffmpeg not found. Set FFMPEG_PATH env or install FFmpeg.")


def which_ffprobe() -> str:
    # 1) Environment override
    env = os.environ.get("FFPROBE_PATH")
    cand = _normalize_exe(env, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if cand:
        return cand
    # 2) PATH
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    # 3) Common relative locations
    here = Path(sys.executable).parent
    for rel in [
        "ffmpeg", "ffmpeg/bin", "bin", "tools/ffmpeg", "vendor/ffmpeg/bin",
    ]:
        p = _normalize_exe(str(here / rel), "ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if p:
            return p
    raise FileNotFoundError("ffprobe not found. Set FFPROBE_PATH env or install FFmpeg.")


def detect_rubberband() -> bool:
    """Return True if ffmpeg exposes the 'rubberband' filter."""
    try:
        out = subprocess.check_output([which_ffmpeg(), "-hide_banner", "-filters"], stderr=subprocess.STDOUT)
        return b"rubberband" in out
    except Exception:
        return False


def probe_media(path: Path) -> ProbeResult:
    """Probe a media file using ffprobe to fetch duration and stream info."""
    cmd = [
        which_ffprobe(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    out = subprocess.check_output(cmd)
    data = json.loads(out.decode("utf-8", errors="replace"))
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0) or 0.0)
    has_video = False
    has_audio = False
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None

    for s in data.get("streams", []):
        codec_type = s.get("codec_type")
        if codec_type == "video":
            has_video = True
        elif codec_type == "audio":
            has_audio = True
            try:
                sample_rate = int(s.get("sample_rate") or 0) or None
            except Exception:
                sample_rate = None
            channels = s.get("channels")
            channel_layout = s.get("channel_layout")

    return ProbeResult(
        duration=duration,
        has_video=has_video,
        has_audio=has_audio,
        sample_rate=sample_rate,
        channels=channels,
        channel_layout=channel_layout,
    )


def build_slowdown_command(
    input_path: Path,
    output_path: Path,
    *,
    duration: float,
    has_video: bool,
    has_audio: bool,
    use_rubberband: bool,
    video_encoder: str = "libx264",
    video_preset: str = "slow",
    video_crf: int = 18,
    audio_codec: str = "aac",
    audio_bitrate: int = 192,
    copy_subtitles: bool = True,
    preview: bool = False,
    preview_seconds: int = 20,
) -> List[str]:
    """Build the ffmpeg command to slow 2x media to 1x."""

    filters: List[str] = []
    maps: List[str] = []

    if has_video:
        filters.append("[0:v]setpts=2*PTS[v]")
        maps.extend(["-map", "[v]"])

    if has_audio:
        if use_rubberband:
            # Preserve formants for natural voice
            filters.append("[0:a]rubberband=tempo=0.5:formant=preserved[a]")
        else:
            # Fallback time-stretch
            filters.append("[0:a]atempo=0.5[a]")
        maps.extend(["-map", "[a]"])

    if not (has_video or has_audio):
        raise ValueError("Input has neither audio nor video streams")

    # Subtitles (if input has them)
    if copy_subtitles and has_video:
        maps.extend(["-map", "0:s?"])

    cmd: List[str] = [
        which_ffmpeg(),
        "-y",
        "-hide_banner",
        "-i",
        str(input_path),
    ]

    # Preview: select a centered 10-20s window for quick A/B
    if preview and duration > 0 and preview_seconds > 0:
        start = max(duration / 2.0 - preview_seconds / 2.0, 0.0)
        # Seek after input for accurate seek
        cmd.extend(["-ss", f"{start:.3f}", "-t", str(int(preview_seconds))])

    if filters:
        cmd.extend(["-filter_complex", ";".join(filters)])

    cmd.extend(maps)

    # Codecs and quality
    if has_video:
        cmd.extend(["-c:v", video_encoder, "-preset", video_preset, "-crf", str(video_crf)])
    if has_audio:
        cmd.extend(["-c:a", audio_codec, "-b:a", f"{int(audio_bitrate)}k"])
    if copy_subtitles and has_video:
        cmd.extend(["-c:s", "copy"])

    # Preserve metadata and chapters
    cmd.extend(["-map_metadata", "0", "-map_chapters", "0"])
    cmd.extend(["-movflags", "+faststart"])  # Fast start for MP4

    cmd.append(str(output_path))
    return cmd


def parse_ffmpeg_time_to_seconds(value: str) -> Optional[float]:
    """Parse ffmpeg time string HH:MM:SS.ms to seconds float."""
    try:
        hh, mm, ss = value.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except Exception:
        return None
