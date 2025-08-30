# Contributing

Thanks for your interest in contributing! This project is a PySide6 + FFmpeg desktop app to batch-slow 2× videos to 1× with high-quality audio.

## Development setup

- Python 3.11+
- Install dependencies:

```
pip install -r requirements.txt
```

- Run the app in dev mode:

```
python -m app.main
```

- If FFmpeg/FFprobe are not on your PATH, use the UI button “Locate FFmpeg…” or set env vars:

```
# Windows (PowerShell)
$env:FFMPEG_PATH="C:\\path\\to\\ffmpeg.exe"
$env:FFPROBE_PATH="C:\\path\\to\\ffprobe.exe"

# macOS/Linux
export FFMPEG_PATH=/usr/local/bin/ffmpeg
export FFPROBE_PATH=/usr/local/bin/ffprobe
```

## Code style

- Prefer type annotations and short, descriptive names.
- Keep UI responsive; long-running tasks must run off the UI thread.
- Minimal, focused changes; avoid incidental refactors in unrelated areas.
- Add docstrings for new modules/classes/functions.

## Testing changes

- Manual: use `tests/gen_demo.py` to create demo inputs; verify output audio sounds natural and subtitles/metadata are preserved.
- If adding progress parsing logic, test with a variety of inputs (video-only, audio-only, with subtitles, VFR).

## Submitting changes

1. Create a feature branch and implement the change with clear commit messages.
2. Update README if user-visible behavior changes (options, defaults, UI).
3. Open a pull request with:
   - Summary of the change and motivation
   - Screenshots/GIFs if UI changes are visible
   - Notes on testing and edge cases

## Reporting issues

When filing an issue, please include:
- OS version (Windows/macOS/Linux) and Python version
- FFmpeg version (`ffmpeg -version`) and whether Rubber Band is available (`ffmpeg -filters | grep rubberband`)
- Steps to reproduce and sample input if possible
- App logs (stored in the app data logs directory for the current session)

## Roadmap ideas

- GPU encoder auto-detection and per-item selection
- Structured progress via `-progress pipe:1`
- Per-item context actions and session persistence

Happy hacking!
