<div align="center">

# Video Slowdown 2x→1x

Batch-convert videos recorded at 2× speed back to natural 1× playback with high audio quality.

Built with Python 3.11, PySide6 (Qt), and FFmpeg. Prefers Rubber Band (formant-preserving) and falls back to `atempo` when not available.

</div>

## Why this tool?

Many screen recorders and camera apps record at 2× to save time but produce robotic audio if naively slowed down. This app batch-processes hundreds of files, slows video properly (`setpts=2*PTS`), and time-stretches audio with Rubber Band (`rubberband=tempo=0.5:formant=preserved`) for natural speech. When Rubber Band isn’t available, it automatically uses `atempo=0.5`.

## Features

- Batch UI: drag & drop folders/files, recursive import
- Queue table: filename, duration, status, progress, ETA, output
- Concurrency: runs up to CPU cores − 1 by default
- Rubber Band detection with automatic fallback to `atempo`
- Video slowing via `setpts=2*PTS`; re-encode with `libx264` by default
- Audio time-stretch with Rubber Band; fallback `atempo=0.5`
- Preserve subtitles/metadata/chapters: `-map 0:s? -c:s copy -map_metadata 0 -map_chapters 0`
- Preview mode: process a centered ~20s clip for quick A/B
- Presets: Visually lossless / Balanced / Smaller file size
- Advanced: encoder, CRF/preset, audio bitrate, optional GPU encoders
- Overwrite toggle, plus safe auto-renaming to avoid skipping
- Rolling log pane and per-session log file

## Quickstart

1) Install Python deps

```
pip install -r requirements.txt
```

2) Ensure FFmpeg and FFprobe are available

- Easiest: put both in your PATH
- Or launch the app and click “Locate FFmpeg…” to select the binary; the app will remember it

3) Run the app

```
python -m app.main
```

4) Add media and start

- Pick Input and Output directories
- Drag a folder into the window (recursively imports .mp4/.mkv/.mov/.m4a/.wav)
- Set Concurrency (defaults to CPU cores − 1)
- Click Start and watch progress/ETA

Outputs mirror the input’s subfolder structure when both Input and Output are set. If output already exists and Overwrite is off, files are written as `_1x`, `_1x(1)`, etc.

## Rubber Band vs. atempo

At launch the app runs `ffmpeg -filters` and shows a badge:

- available: uses `rubberband=tempo=0.5:formant=preserved`
- unavailable: falls back to `atempo=0.5` and warns once

Enable Rubber Band:

- Windows: use an FFmpeg build with `librubberband` (e.g., Gyan.dev full builds)
- macOS (Homebrew): `brew install ffmpeg rubberband`
- Linux: distro builds often ship Rubber Band; otherwise install the `rubberband` package and rebuild FFmpeg accordingly

## How it works

- Video: `[0:v]setpts=2*PTS[v]` (preserves all frames, doubles duration)
- Audio (preferred): `[0:a]rubberband=tempo=0.5:formant=preserved[a]`
- Audio (fallback): `[0:a]atempo=0.5[a]`
- Subtitles: `-map 0:s? -c:s copy`; metadata/chapters copied
- Defaults: `-c:v libx264 -preset slow -crf 18`, `-c:a aac -b:a 192k`, `-movflags +faststart`

Example with Rubber Band:

```
ffmpeg -y -i IN -filter_complex "[0:v]setpts=2*PTS[v];[0:a]rubberband=tempo=0.5:formant=preserved[a]" \
  -map "[v]" -map "[a]" -map 0:s? -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k \
  -c:s copy -map_metadata 0 -map_chapters 0 -movflags +faststart OUT
```

## GPU encoders

Select `h264_nvenc` (NVIDIA), `h264_qsv` (Intel Quick Sync), or `h264_videotoolbox` (macOS) in Advanced. Availability depends on your FFmpeg build and hardware.

## Troubleshooting

- ffprobe not found / ffmpeg not found
  - Click “Locate FFmpeg…” and point to your ffmpeg binary; the app tries to find ffprobe in the same folder
  - Or set env vars: `FFMPEG_PATH`, `FFPROBE_PATH`
- Rubber Band unavailable
  - Use an FFmpeg build with `librubberband` enabled (see above). The app will fall back to `atempo` automatically
- Outputs skipped due to existing files
  - With Overwrite off, the app now auto-renames to `_1x`, `_1x(1)`, etc.
- Pause/Resume
  - If `psutil` is present and the OS supports suspend/resume, active encodes pause. Otherwise, only queue pausing is supported

## Test dataset generator

Create simple 2× demo clips for A/B testing:

```
python tests/gen_demo.py
```

Outputs to `./demo`: `demo_video_2x.mp4`, `demo_audio_2x.m4a`.

## Packaging

### Windows (PyInstaller)

```
pip install pyinstaller
pyinstaller --noconfirm --name VideoSlowdown --windowed --onefile \
  --add-data "app/resources/style.qss;app/resources" \
  -p . app/main.py
```

- For one-folder, drop `--onefile`
- Ensure `ffmpeg.exe` and `ffprobe.exe` are on PATH at runtime or ship them next to the EXE and use “Locate FFmpeg…” once

### macOS

```
pyinstaller --noconfirm --name VideoSlowdown --windowed \
  --add-data "app/resources/style.qss:app/resources" \
  -p . app/main.py
```

### Linux

Use the macOS command form (note the `:` path separator in `--add-data`). Ensure FFmpeg is installed.

## Development

Project structure:

```
app/
  core/
    config.py       # JSON settings, app data dir
    ffmpeg.py       # probe, rubberband detection, command build
    models.py       # Job model and status
    workers.py      # JobManager + ProcessorWorker with progress parsing
  resources/
    style.qss       # dark theme stylesheet
  ui/
    main_window.py  # PySide6 UI and integration
  main.py           # entrypoint (supports module/script launch)
tests/
  gen_demo.py       # demo dataset generator
requirements.txt
README.md
```

Run in dev:

```
python -m app.main
```

Coding guidelines:

- Python 3.11+, type hints and docstrings encouraged
- Keep UI responsive: long work in background threads (QThreadPool)
- Avoid breaking presets/advanced defaults; prefer additive changes

## Roadmap

- Auto-detect available GPU encoders at startup (parse `ffmpeg -encoders`)
- Per-item context menu: Retry, Reveal in Explorer/Finder
- Switch to `-progress pipe:1` for structured progress parsing
- More output formats (copy codec for audio-only inputs when safe)

---

No license specified. If you plan to publish publicly, add a license file suitable for your use.
