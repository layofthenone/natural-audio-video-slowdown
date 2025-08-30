from __future__ import annotations

import os
import math
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from app.core.config import AppSettings, SettingsStore
from app.core.ffmpeg import (
    detect_rubberband,
    probe_media,
    build_slowdown_command,
)
from app.core.models import Job, JobStatus
from app.core.workers import JobManager


SUPPORTED_EXTS = {".mp4", ".mkv", ".mov", ".m4a", ".wav"}


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Slowdown 2x→1x")
        self.setAcceptDrops(True)

        # Settings
        self.store = SettingsStore()
        self.settings = self.store.load()

        # State
        self.jobs: List[Job] = []
        self.next_job_id = 1
        self.rubberband_available = detect_rubberband()

        # UI
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        self.vbox = QtWidgets.QVBoxLayout(central)

        self._build_top_controls()
        self._build_table()
        self._build_log()
        self._build_status_bar()

        # Job manager
        self.manager = JobManager(self._default_concurrency())
        self.manager.job_progress.connect(self._on_job_progress)
        self.manager.job_log.connect(self._on_job_log)
        self.manager.job_status.connect(self._on_job_status)
        self.manager.queue_finished.connect(self._on_queue_finished)

        # Load settings to UI
        self._apply_settings_to_ui()

        # Session log file
        logs_dir = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppLocalDataLocation)) / "VideoSlowdown" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = logs_dir / (QtCore.QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss") + ".log")  # type: ignore[arg-type]
        self._log_fp = open(self.log_path, "w", encoding="utf-8")

        if not self.rubberband_available:
            self.status.showMessage("Rubber Band filter unavailable; falling back to atempo.", 8000)

    def _build_top_controls(self) -> None:
        box = QtWidgets.QGroupBox("Batch Settings")
        grid = QtWidgets.QGridLayout(box)

        self.input_edit = QtWidgets.QLineEdit()
        self.output_edit = QtWidgets.QLineEdit()
        btn_in = QtWidgets.QPushButton("Browse…")
        btn_out = QtWidgets.QPushButton("Browse…")
        btn_in.clicked.connect(self._choose_input_dir)
        btn_out.clicked.connect(self._choose_output_dir)

        self.overwrite_chk = QtWidgets.QCheckBox("Overwrite existing")
        self.copy_subs_chk = QtWidgets.QCheckBox("Copy subtitles")
        self.copy_subs_chk.setChecked(True)

        self.concurrency_spin = QtWidgets.QSpinBox()
        self.concurrency_spin.setRange(1, max(1, os.cpu_count() or 4))
        self.concurrency_spin.setValue(self._default_concurrency())
        self.concurrency_spin.valueChanged.connect(self._on_concurrency_changed)

        self.preview_chk = QtWidgets.QCheckBox("Preview 20s clip")
        self.preview_chk.setChecked(False)

        self.rb_badge = QtWidgets.QLabel(
            "Rubber Band: "
            + ("available" if self.rubberband_available else "unavailable – using atempo")
        )
        self.rb_badge.setStyleSheet(
            "color: #7ee787;" if self.rubberband_available else "color: #ffa657;"
        )
        self.locate_btn = QtWidgets.QPushButton("Locate FFmpeg…")
        self.locate_btn.clicked.connect(self._locate_ffmpeg)

        # Presets
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(["Visually lossless", "Balanced", "Smaller file size"])
        self.preset_combo.setCurrentText("Balanced")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

        # Advanced
        self.encoder_combo = QtWidgets.QComboBox()
        self.encoder_combo.addItems(["libx264", "h264_nvenc", "h264_qsv", "h264_videotoolbox"])
        self.gpu_chk = QtWidgets.QCheckBox("Use GPU encoder if selected")
        self.preset_edit = QtWidgets.QComboBox()
        self.preset_edit.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.preset_edit.setCurrentText("slow")
        self.crf_spin = QtWidgets.QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(18)
        self.audio_bitrate_spin = QtWidgets.QSpinBox()
        self.audio_bitrate_spin.setRange(64, 512)
        self.audio_bitrate_spin.setValue(192)

        # Buttons
        self.btn_add = QtWidgets.QPushButton("Add Folder…")
        self.btn_add.clicked.connect(self._add_folder)
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_resume = QtWidgets.QPushButton("Resume")
        self.btn_cancel = QtWidgets.QPushButton("Cancel Selected")
        self.btn_retry = QtWidgets.QPushButton("Retry Selected")

        self.btn_start.clicked.connect(self._start_queue)
        self.btn_pause.clicked.connect(self._pause_queue)
        self.btn_resume.clicked.connect(self._resume_queue)
        self.btn_cancel.clicked.connect(self._cancel_selected)
        self.btn_retry.clicked.connect(self._retry_selected)

        # Layout
        r = 0
        grid.addWidget(QtWidgets.QLabel("Input Directory"), r, 0)
        grid.addWidget(self.input_edit, r, 1)
        grid.addWidget(btn_in, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Output Directory"), r, 0)
        grid.addWidget(self.output_edit, r, 1)
        grid.addWidget(btn_out, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Concurrency"), r, 0)
        grid.addWidget(self.concurrency_spin, r, 1)
        grid.addWidget(self.rb_badge, r, 2)
        grid.addWidget(self.locate_btn, r, 3)
        r += 1
        grid.addWidget(self.overwrite_chk, r, 0)
        grid.addWidget(self.copy_subs_chk, r, 1)
        grid.addWidget(self.preview_chk, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Preset"), r, 0)
        grid.addWidget(self.preset_combo, r, 1)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Encoder"), r, 0)
        grid.addWidget(self.encoder_combo, r, 1)
        grid.addWidget(self.gpu_chk, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("CRF"), r, 0)
        grid.addWidget(self.crf_spin, r, 1)
        grid.addWidget(QtWidgets.QLabel("Preset"), r, 2)
        grid.addWidget(self.preset_edit, r, 3)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Audio kbps"), r, 0)
        grid.addWidget(self.audio_bitrate_spin, r, 1)
        r += 1
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.btn_add)
        hl.addStretch(1)
        hl.addWidget(self.btn_start)
        hl.addWidget(self.btn_pause)
        hl.addWidget(self.btn_resume)
        hl.addWidget(self.btn_cancel)
        hl.addWidget(self.btn_retry)
        grid.addLayout(hl, r, 0, 1, 4)

        self.vbox.addWidget(box)

    def _build_table(self) -> None:
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Filename",
            "Duration",
            "Status",
            "Progress",
            "ETA",
            "Output",
            "Message",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.vbox.addWidget(self.table, 1)

    def _build_log(self) -> None:
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        self.vbox.addWidget(self.log)

    def _build_status_bar(self) -> None:
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _apply_settings_to_ui(self) -> None:
        s = self.settings
        if s.input_dir:
            self.input_edit.setText(s.input_dir)
        if s.output_dir:
            self.output_edit.setText(s.output_dir)
        if s.concurrent_jobs > 0:
            self.concurrency_spin.setValue(s.concurrent_jobs)
        self.overwrite_chk.setChecked(s.overwrite)
        self.copy_subs_chk.setChecked(s.copy_subtitles)
        self.preview_chk.setChecked(s.preview_enabled)
        self.preset_combo.setCurrentText(s.preset)
        self.encoder_combo.setCurrentText(s.video_encoder)
        self.preset_edit.setCurrentText(s.video_preset)
        self.crf_spin.setValue(s.video_crf)
        self.audio_bitrate_spin.setValue(s.audio_bitrate)
        self.gpu_chk.setChecked(s.gpu_enabled)
        # If explicit ffmpeg/ffprobe paths are set, export to env so core resolves correctly
        if s.ffmpeg_path:
            os.environ["FFMPEG_PATH"] = s.ffmpeg_path
        if s.ffprobe_path:
            os.environ["FFPROBE_PATH"] = s.ffprobe_path

    def _collect_settings(self) -> AppSettings:
        s = AppSettings(
            input_dir=self.input_edit.text().strip(),
            output_dir=self.output_edit.text().strip(),
            concurrent_jobs=int(self.concurrency_spin.value()),
            overwrite=self.overwrite_chk.isChecked(),
            preset=self.preset_combo.currentText(),
            video_encoder=self.encoder_combo.currentText(),
            video_preset=self.preset_edit.currentText(),
            video_crf=int(self.crf_spin.value()),
            audio_codec="aac",
            audio_bitrate=int(self.audio_bitrate_spin.value()),
            copy_subtitles=self.copy_subs_chk.isChecked(),
            preview_enabled=self.preview_chk.isChecked(),
            preview_seconds=20,
            gpu_enabled=self.gpu_chk.isChecked(),
            ffmpeg_path=os.environ.get("FFMPEG_PATH", ""),
            ffprobe_path=os.environ.get("FFPROBE_PATH", ""),
        )
        return s

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self.settings = self._collect_settings()
        self.store.save(self.settings)
        try:
            self._log_fp.close()
        except Exception:
            pass
        super().closeEvent(event)

    # Drag & Drop
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            paths.append(p)
        self._add_paths(paths)

    # Actions
    def _choose_input_dir(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Input Directory")
        if d:
            self.input_edit.setText(d)

    def _choose_output_dir(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if d:
            self.output_edit.setText(d)

    def _default_concurrency(self) -> int:
        n = (os.cpu_count() or 4) - 1
        return max(1, n)

    def _on_concurrency_changed(self, value: int) -> None:
        self.manager.set_concurrency(int(value))

    def _on_preset_changed(self) -> None:
        p = self.preset_combo.currentText()
        if p == "Visually lossless":
            self.crf_spin.setValue(16)
            self.preset_edit.setCurrentText("slow")
            self.audio_bitrate_spin.setValue(224)
        elif p == "Balanced":
            self.crf_spin.setValue(18)
            self.preset_edit.setCurrentText("slow")
            self.audio_bitrate_spin.setValue(192)
        elif p == "Smaller file size":
            self.crf_spin.setValue(22)
            self.preset_edit.setCurrentText("medium")
            self.audio_bitrate_spin.setValue(128)

    def _file_iter(self, root: Path) -> List[Path]:
        if root.is_file():
            return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
        files: List[Path] = []
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                files.append(p)
        return files

    def _add_folder(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder to Add")
        if d:
            self._add_paths([Path(d)])

    def _add_paths(self, paths: List[Path]) -> None:
        input_dir = Path(self.input_edit.text().strip()) if self.input_edit.text().strip() else None
        output_dir = Path(self.output_edit.text().strip()) if self.output_edit.text().strip() else None
        row_added = 0
        for p in paths:
            files = self._file_iter(p)
            for f in files:
                row_added += 1
                out = self._derive_output_path(f, input_dir, output_dir)
                self._append_job_row(f, out)
        if row_added:
            self.status.showMessage(f"Added {row_added} item(s) to queue", 5000)

    def _derive_output_path(
        self, file_path: Path, input_dir: Optional[Path], output_dir: Optional[Path]
    ) -> Path:
        # If both dirs set and file is under input, mirror into output
        if output_dir and input_dir and (file_path.is_relative_to(input_dir)):
            # If output and input are the same folder, avoid clobbering by adding suffix
            try:
                same_root = output_dir.resolve() == input_dir.resolve()
            except Exception:
                same_root = str(output_dir) == str(input_dir)
            if same_root:
                return file_path.with_stem(file_path.stem + "_1x")
            return output_dir / file_path.relative_to(input_dir)
        if output_dir:
            # Output dir set but file not under input dir; place at root of output
            return output_dir / file_path.name
        # Fallback: same folder, add suffix
        return file_path.with_stem(file_path.stem + "_1x")

    def _unique_output_path(self, base: Path) -> Path:
        """Return a non-existing path by appending _1x or _1x(n)."""
        if not base.exists():
            return base
        # If base already has _1x, start numbering
        stem = base.stem
        suffix = base.suffix
        if not stem.endswith("_1x"):
            candidate = base.with_stem(stem + "_1x")
            if not candidate.exists():
                return candidate
            stem = stem + "_1x"
        for i in range(1, 1000):
            candidate = base.with_stem(f"{stem}({i})")
            if not candidate.exists():
                return candidate
        # As a last resort, timestamp
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return base.with_stem(f"{stem}_{ts}")

    def _append_job_row(self, in_path: Path, out_path: Path) -> None:
        job_id = self.next_job_id
        self.next_job_id += 1
        job = Job(job_id, in_path, out_path)
        self.jobs.append(job)

        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(in_path)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(job.status.value))
        self._set_progress_cell(r, 0.0)
        self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(out_path)))
        self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(""))

    def _set_progress_cell(self, row: int, progress: float) -> None:
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(progress * 100))
        self.table.setCellWidget(row, 3, bar)

    def _start_queue(self) -> None:
        self.settings = self._collect_settings()
        self.store.save(self.settings)

        # Prepare jobs: probe, compute command, skip existing unless overwrite
        overwrite = self.settings.overwrite
        copy_subs = self.settings.copy_subtitles
        any_started = False
        for idx, job in enumerate(self.jobs):
            if job.status not in {JobStatus.PENDING, JobStatus.SKIPPED, JobStatus.FAILED, JobStatus.CANCELED}:
                continue
            # Probe
            try:
                pr = probe_media(job.input_path)
                job.duration = pr.duration
                job.has_video = pr.has_video
                job.has_audio = pr.has_audio
                # Update duration cell
                self.table.item(idx, 1).setText(self._format_time(job.duration))
            except Exception as e:
                job.mark_failed(f"Probe failed: {e}")
                self.table.item(idx, 2).setText(job.status.value)
                self.table.item(idx, 6).setText(job.message)
                # Offer quick fix if ffprobe missing
                msg = str(e).lower()
                if "ffprobe" in msg and "not found" in msg:
                    QtWidgets.QMessageBox.warning(self, "FFprobe not found", "FFprobe was not found. Click 'Locate FFmpeg…' to set its path.")
                continue

            # Ensure output directory exists
            job.output_path.parent.mkdir(parents=True, exist_ok=True)

            if job.output_path.exists() and not overwrite:
                # Auto-generate a non-conflicting output instead of skipping
                new_out = self._unique_output_path(job.output_path)
                job.output_path = new_out
                self.table.setItem(idx, 5, QtWidgets.QTableWidgetItem(str(new_out)))

            # Build command
            cmd = build_slowdown_command(
                job.input_path,
                job.output_path,
                duration=job.duration,
                has_video=job.has_video,
                has_audio=job.has_audio,
                use_rubberband=self.rubberband_available and job.has_audio,
                video_encoder=self.settings.video_encoder,
                video_preset=self.settings.video_preset,
                video_crf=self.settings.video_crf,
                audio_codec=self.settings.audio_codec,
                audio_bitrate=self.settings.audio_bitrate,
                copy_subtitles=copy_subs,
                preview=self.settings.preview_enabled,
                preview_seconds=self.settings.preview_seconds,
            )
            job.command = cmd

            # Enqueue
            self.manager.add_job(job)
            job.status = JobStatus.QUEUED
            self.table.item(idx, 2).setText(job.status.value)
            any_started = True

        if any_started:
            self.status.showMessage("Processing started", 5000)
        else:
            self.status.showMessage("Nothing to process", 5000)

    def _pause_queue(self) -> None:
        self.manager.pause_queue()
        self.status.showMessage("Queue paused (active jobs may pause if supported)", 5000)

    def _resume_queue(self) -> None:
        self.manager.resume_queue()
        self.status.showMessage("Queue resumed", 5000)

    def _cancel_selected(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        for r in rows:
            job = self.jobs[r]
            self.manager.cancel_job(job.id)
            job.mark_canceled()
            self.table.item(r, 2).setText(job.status.value)
            self.table.item(r, 6).setText("Canceled by user")

    def _retry_selected(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        for r in rows:
            job = self.jobs[r]
            if job.status in {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.SKIPPED}:
                job.status = JobStatus.PENDING
                job.progress = 0.0
                self._set_progress_cell(r, 0.0)
                self.table.item(r, 2).setText(job.status.value)
                self.table.item(r, 6).setText("")

    # Manager slots
    def _on_job_progress(self, job_id: int, prog: float, eta: float) -> None:
        idx = self._index_by_job_id(job_id)
        if idx is None:
            return
        self._set_progress_cell(idx, prog)
        self.table.setItem(idx, 4, QtWidgets.QTableWidgetItem(self._format_eta(eta)))

    def _on_job_log(self, job_id: int, line: str) -> None:
        idx = self._index_by_job_id(job_id)
        self.log.appendPlainText(f"[{job_id}] {line}")
        try:
            self._log_fp.write(f"[{job_id}] {line}\n")
        except Exception:
            pass
        if idx is not None:
            self.table.setItem(idx, 6, QtWidgets.QTableWidgetItem(line[:200]))

    def _on_job_status(self, job_id: int, status: str) -> None:
        idx = self._index_by_job_id(job_id)
        if idx is not None:
            self.table.setItem(idx, 2, QtWidgets.QTableWidgetItem(status))

    def _on_queue_finished(self) -> None:
        self.status.showMessage("All tasks finished", 7000)

    def _locate_ffmpeg(self) -> None:
        # Ask for ffmpeg executable
        if sys.platform == "win32":
            filt = "FFmpeg (ffmpeg.exe) (*.exe)"
        else:
            filt = "FFmpeg (ffmpeg)"  # show all files
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Locate ffmpeg executable", "", filt)
        if not path:
            return
        ffmpeg_path = Path(path)
        ffprobe_candidate = ffmpeg_path.parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        os.environ["FFMPEG_PATH"] = str(ffmpeg_path)
        if ffprobe_candidate.exists():
            os.environ["FFPROBE_PATH"] = str(ffprobe_candidate)
        self.settings = self._collect_settings()
        self.settings.ffmpeg_path = os.environ.get("FFMPEG_PATH", "")
        self.settings.ffprobe_path = os.environ.get("FFPROBE_PATH", "")
        self.store.save(self.settings)
        # Re-check Rubber Band availability
        from app.core.ffmpeg import detect_rubberband

        self.rubberband_available = detect_rubberband()
        self.rb_badge.setText(
            "Rubber Band: " + ("available" if self.rubberband_available else "unavailable – using atempo")
        )
        self.rb_badge.setStyleSheet("color: #7ee787;" if self.rubberband_available else "color: #ffa657;")

    def _index_by_job_id(self, job_id: int) -> Optional[int]:
        for idx, j in enumerate(self.jobs):
            if j.id == job_id:
                return idx
        return None

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds <= 0:
            return "?"
        m, s = divmod(int(seconds + 0.5), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if not math.isfinite(seconds) or seconds < 0:
            return "?"
        m, s = divmod(int(seconds + 0.5), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
