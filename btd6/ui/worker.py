from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from btd6.ui.scheduler import Scheduler

POLL_INTERVAL_MS = 50

Work = Callable[[Callable[[str], None]], Any]
StartThread = Callable[[Callable[[], None]], None]


def start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


@dataclass
class Job:
    on_success: Callable[[Any], None]
    on_error: Callable[[Exception], None]
    on_progress: Callable[[str], None] | None


class BackgroundRunner:
    """Run work off the UI thread; callbacks fire on the thread that calls `poll`.

    The scheduler (Tk's `after`) drives polling, so callbacks always run on the main
    thread. Work receives a `report(text)` function for progress messages.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        start_thread: StartThread = start_daemon_thread,
        poll_interval_ms: int = POLL_INTERVAL_MS,
    ) -> None:
        self._scheduler = scheduler
        self._start_thread = start_thread
        self._poll_interval_ms = poll_interval_ms
        self._messages: queue.Queue[tuple[int, str, Any]] = queue.Queue()
        self._jobs: dict[int, Job] = {}
        self._next_id = 0
        self._poll_token: str | None = None
        self._closed = False

    def submit(
        self,
        work: Work,
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        if self._closed:
            return
        self._next_id += 1
        job_id = self._next_id
        self._jobs[job_id] = Job(on_success, on_error, on_progress)
        self._start_thread(lambda: self._execute(job_id, work))
        self._ensure_polling()

    def _execute(self, job_id: int, work: Work) -> None:
        def report(text: str) -> None:
            self._messages.put((job_id, "progress", text))

        try:
            result = work(report)
        except Exception as error:
            self._messages.put((job_id, "error", error))
        else:
            self._messages.put((job_id, "done", result))

    def _ensure_polling(self) -> None:
        if self._poll_token is None:
            self._poll_token = self._scheduler.after(self._poll_interval_ms, self.poll)

    def poll(self) -> None:
        self._poll_token = None
        while True:
            try:
                job_id, kind, payload = self._messages.get_nowait()
            except queue.Empty:
                break
            self._dispatch(job_id, kind, payload)
        if self._jobs and not self._closed:
            self._ensure_polling()

    def _dispatch(self, job_id: int, kind: str, payload: object) -> None:
        background_job = self._jobs.get(job_id)
        if background_job is None or self._closed:
            return
        if kind == "progress":
            if background_job.on_progress is not None:
                background_job.on_progress(payload)
            return
        del self._jobs[job_id]
        (background_job.on_success if kind == "done" else background_job.on_error)(payload)

    def close(self) -> None:
        self._closed = True
        self._jobs.clear()
        if self._poll_token is not None:
            self._scheduler.after_cancel(self._poll_token)
            self._poll_token = None
