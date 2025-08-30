from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6 import QtCore

from .models import Job, JobStatus
from .ffmpeg import parse_ffmpeg_time_to_seconds


class ProcessorSignals(QtCore.QObject):
    progress = QtCore.Signal(int, float, float)  # job_id, progress 0..1, eta_seconds
    status = QtCore.Signal(int, str)  # job_id, status text
    log = QtCore.Signal(int, str)  # job_id, log line
    started = QtCore.Signal(int, int)  # job_id, pid
    finished = QtCore.Signal(int, bool, str)  # job_id, success, message


class ProcessorWorker(QtCore.QRunnable):
    """Runs a single ffmpeg process in a background thread and reports progress."""

    def __init__(self, job: Job) -> None:
        super().__init__()
        self.job = job
        self.signals = ProcessorSignals()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_supported = False
        try:
            import psutil  # type: ignore

            self._pause_supported = True
        except Exception:
            self._pause_supported = False

        self._process: Optional[subprocess.Popen] = None

    @QtCore.Slot()
    def run(self) -> None:  # type: ignore[override]
        job = self.job
        job.mark_running()
        self.signals.status.emit(job.id, JobStatus.RUNNING.value)

        start_time = time.time()
        # ffmpeg reports processed (output) timestamp in stderr for most filters
        # Our output is 2x the input duration when slowing 2x->1x
        duration = max(job.duration * 2.0, 0.01)

        # Launch process
        try:
            self._process = subprocess.Popen(
                job.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )
        except Exception as e:
            self.signals.finished.emit(job.id, False, f"Failed to start ffmpeg: {e}")
            return

        job.ffmpeg_pid = self._process.pid
        self.signals.started.emit(job.id, job.ffmpeg_pid or -1)

        # Progress reading thread from stderr
        current_time_seconds = 0.0

        assert self._process.stderr is not None
        for line in self._process.stderr:
            if self._stop_event.is_set():
                break

            # Honor pause by suspending process if supported
            if self._pause_event.is_set():
                if self._pause_supported and self._process and self._process.pid:
                    try:
                        import psutil  # type: ignore

                        psutil.Process(self._process.pid).suspend()
                    except Exception:
                        pass
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                if self._pause_supported and self._process and self._process.pid:
                    try:
                        import psutil  # type: ignore

                        psutil.Process(self._process.pid).resume()
                    except Exception:
                        pass

            line = line.strip()
            if not line:
                continue
            self.signals.log.emit(job.id, line)

            # Typical stderr line contains time=HH:MM:SS.ms
            if "time=" in line:
                try:
                    # find last occurrence to be robust
                    token = line.split("time=")[-1].split()[0]
                    t = parse_ffmpeg_time_to_seconds(token)
                    if t is not None:
                        current_time_seconds = t
                        prog = min(max(current_time_seconds / duration, 0.0), 1.0)
                        elapsed = max(time.time() - start_time, 0.001)
                        # Effective processing speed (output seconds per real second)
                        speed = (current_time_seconds) / elapsed if elapsed > 0 else 0.0
                        rem = (duration - current_time_seconds) / max(speed, 0.01)
                        self.signals.progress.emit(job.id, prog, rem)
                except Exception:
                    pass

        # Wait for process to finish
        ret = None
        if self._process:
            try:
                ret = self._process.wait(timeout=1)
            except Exception:
                ret = -1

        stopped = self._stop_event.is_set()
        if stopped:
            self.signals.finished.emit(job.id, False, "Canceled")
        else:
            ok = ret == 0
            self.signals.finished.emit(job.id, ok, "OK" if ok else f"ffmpeg exited with code {ret}")

    def cancel(self) -> None:
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                if sys.platform == "win32":
                    self._process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    self._process.terminate()
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()


class JobManager(QtCore.QObject):
    """Coordinates job queue execution with limited concurrency using QThreadPool."""

    job_updated = QtCore.Signal(int)  # job_id
    job_progress = QtCore.Signal(int, float, float)
    job_log = QtCore.Signal(int, str)
    job_status = QtCore.Signal(int, str)
    queue_finished = QtCore.Signal()

    def __init__(self, max_workers: int = 1) -> None:
        super().__init__()
        self.pool = QtCore.QThreadPool.globalInstance()
        self.max_workers = max(1, int(max_workers))
        self.pending: queue.Queue[Job] = queue.Queue()
        self.active: dict[int, ProcessorWorker] = {}
        self._paused = False

    def set_concurrency(self, n: int) -> None:
        self.max_workers = max(1, n)
        self._maybe_dispatch()

    def add_job(self, job: Job) -> None:
        self.pending.put(job)
        self._maybe_dispatch()

    def pause_queue(self) -> None:
        self._paused = True

    def resume_queue(self) -> None:
        self._paused = False
        # resume active workers
        for w in list(self.active.values()):
            w.resume()
        self._maybe_dispatch()

    def cancel_job(self, job_id: int) -> None:
        w = self.active.get(job_id)
        if w:
            w.cancel()

    def pause_job(self, job_id: int) -> None:
        w = self.active.get(job_id)
        if w:
            w.pause()

    def resume_job(self, job_id: int) -> None:
        w = self.active.get(job_id)
        if w:
            w.resume()

    def _maybe_dispatch(self) -> None:
        if self._paused:
            return
        while len(self.active) < self.max_workers and not self.pending.empty():
            job = self.pending.get()
            worker = ProcessorWorker(job)
            worker.signals.progress.connect(self._on_progress)
            worker.signals.log.connect(self._on_log)
            worker.signals.status.connect(self._on_status)
            worker.signals.started.connect(self._on_started)
            worker.signals.finished.connect(self._on_finished)

            self.active[job.id] = worker
            self.pool.start(worker)

    @QtCore.Slot(int, float, float)
    def _on_progress(self, job_id: int, prog: float, eta: float) -> None:
        self.job_progress.emit(job_id, prog, eta)

    @QtCore.Slot(int, str)
    def _on_log(self, job_id: int, line: str) -> None:
        self.job_log.emit(job_id, line)

    @QtCore.Slot(int, str)
    def _on_status(self, job_id: int, status: str) -> None:
        self.job_status.emit(job_id, status)

    @QtCore.Slot(int, int)
    def _on_started(self, job_id: int, pid: int) -> None:
        self.job_status.emit(job_id, f"PID {pid}")

    @QtCore.Slot(int, bool, str)
    def _on_finished(self, job_id: int, ok: bool, message: str) -> None:
        # Clean active and try next
        self.active.pop(job_id, None)
        self.job_status.emit(job_id, "Completed" if ok else f"Failed: {message}")
        self._maybe_dispatch()
        if not self.active and self.pending.empty():
            self.queue_finished.emit()
