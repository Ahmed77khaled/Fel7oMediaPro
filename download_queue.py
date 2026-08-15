"""Small in-process download queue with one active job per Telegram user."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time
import uuid
from typing import Callable


@dataclass
class DownloadJob:
    job_id: str
    chat_id: int
    label: str
    action: Callable[[], None]
    created_at: float
    cancelled: bool = False
    started: bool = False


class DownloadQueue:
    def __init__(self, worker_count: int = 2):
        self.worker_count = max(1, worker_count)
        self._jobs: deque[DownloadJob] = deque()
        self._known_jobs: dict[str, DownloadJob] = {}
        self._active_chat_ids: set[int] = set()
        self._condition = threading.Condition()
        self._started = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
            for index in range(self.worker_count):
                threading.Thread(
                    target=self._worker,
                    name=f"download-queue-{index + 1}",
                    daemon=True,
                ).start()

    def enqueue(self, chat_id: int, label: str, action: Callable[[], None]) -> tuple[DownloadJob, int]:
        job = DownloadJob(
            job_id=uuid.uuid4().hex[:12],
            chat_id=chat_id,
            label=label,
            action=action,
            created_at=time.time(),
        )
        with self._condition:
            self._jobs.append(job)
            self._known_jobs[job.job_id] = job
            position = sum(1 for queued_job in self._jobs if queued_job.chat_id == chat_id)
            if chat_id in self._active_chat_ids:
                position += 1
            self._condition.notify_all()
        return job, position

    def cancel(self, chat_id: int, job_id: str) -> str:
        with self._condition:
            job = self._known_jobs.get(job_id)
            if not job or job.chat_id != chat_id:
                return "missing"
            if job.started:
                return "active"
            if job.cancelled:
                return "cancelled"
            job.cancelled = True
            self._condition.notify_all()
            return "cancelled"

    def _next_job(self) -> DownloadJob | None:
        for job in tuple(self._jobs):
            if job.cancelled:
                self._jobs.remove(job)
                self._known_jobs.pop(job.job_id, None)
                continue
            if job.chat_id in self._active_chat_ids:
                continue
            self._jobs.remove(job)
            job.started = True
            self._active_chat_ids.add(job.chat_id)
            return job
        return None

    def _worker(self) -> None:
        while True:
            with self._condition:
                job = self._next_job()
                while job is None:
                    self._condition.wait()
                    job = self._next_job()
            try:
                job.action()
            except Exception as error:
                print(f"[Queue] Job {job.job_id} failed: {error}")
            finally:
                with self._condition:
                    self._active_chat_ids.discard(job.chat_id)
                    self._known_jobs.pop(job.job_id, None)
                    self._condition.notify_all()
