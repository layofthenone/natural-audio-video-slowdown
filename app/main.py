from __future__ import annotations

import sys
from PySide6 import QtWidgets, QtGui, QtCore
from pathlib import Path
import os
import sys as _sys

# Support running as `python -m app.main` and `python app/main.py`
if __package__ in (None, ""):
    _this_dir = Path(__file__).resolve().parent
    _parent = _this_dir.parent
    if str(_parent) not in _sys.path:
        _sys.path.insert(0, str(_parent))
    from app.ui.main_window import MainWindow  # type: ignore
else:
    from .ui.main_window import MainWindow


def main() -> int:
    """Entry point to start the Qt application."""
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Video Slowdown 2x→1x")
    app.setOrganizationName("OpenAI-Codex")

    # High DPI awareness
    try:
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)  # type: ignore[attr-defined]
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
    except Exception:
        pass

    # Load dark stylesheet relative to this file
    try:
        style_path = Path(__file__).resolve().parent / "resources" / "style.qss"
        if style_path.exists():
            app.setStyleSheet(style_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
