from __future__ import annotations

import enum
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
import time


class JobStatus(enum.Enum):
    PENDING = "Pending"
    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELED = "Canceled"
    SKIPPED = "Skipped"


@dataclass
class Job:
    """Represents a media processing job for a single input file."""

    id: int
    input_path: Path
    output_path: Path
    status: JobStatus = JobStatus.PENDING
    duration: float = 0.0  # seconds
    has_video: bool = False
    has_audio: bool = False
    progress: float = 0.0  # 0..1
    eta_seconds: Optional[float] = None
    message: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    ffmpeg_pid: Optional[int] = None
    preview_mode: bool = False
    command: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.start_time = time.time()
        self.progress = 0.0
        self.eta_seconds = None

    def mark_completed(self) -> None:
        self.status = JobStatus.COMPLETED
        self.progress = 1.0
        self.end_time = time.time()

    def mark_failed(self, message: str) -> None:
        self.status = JobStatus.FAILED
        self.message = message
        self.end_time = time.time()

    def mark_canceled(self) -> None:
        self.status = JobStatus.CANCELED
        self.end_time = time.time()

