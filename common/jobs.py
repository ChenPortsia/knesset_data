"""Run one background command at a time and track it. Used by each service's API.

One at a time because DuckDB allows one writer per database file.
Jobs live in memory: a restart forgets them, but their log files stay in logs/.
"""

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Job:
    job_id: str
    command: list[str]
    log_file: str
    status: str = "running"  # running | succeeded | failed
    started_at: datetime = field(default_factory=now)
    finished_at: datetime | None = None
    exit_code: int | None = None
    result: dict[str, Any] | None = None  # filled in by the service when the job ends


class Runner:
    def __init__(
        self,
        log_dir: Path,
        cwd: Path | None = None,
        on_finish: Callable[[Job], dict[str, Any] | None] | None = None,
    ) -> None:
        self.log_dir, self.cwd, self.on_finish = log_dir, cwd, on_finish
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    @property
    def current(self) -> Job | None:
        return next((job for job in self.jobs.values() if job.status == "running"), None)

    def start(self, job_id: str, command: list[str]) -> Job | None:
        """Start a job in the background; None if another job is still running."""
        with self._lock:
            if self.current:
                return None
            self.log_dir.mkdir(parents=True, exist_ok=True)
            job = Job(job_id, command, str(self.log_dir / f"{job_id}.out"))
            self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        with open(job.log_file, "w", encoding="utf-8") as log:
            try:
                code = subprocess.run(
                    job.command, cwd=self.cwd, stdout=log, stderr=subprocess.STDOUT
                ).returncode
            except OSError as error:  # e.g. the command does not exist
                log.write(f"could not start: {error}\n")
                code = 127
        if self.on_finish:
            try:
                job.result = self.on_finish(job)
            except Exception as error:  # a broken summary must not hide the job's outcome
                job.result = {"summary_error": str(error)}
        job.exit_code, job.finished_at = code, now()
        job.status = "succeeded" if code == 0 else "failed"


def tail(path: str | Path, lines: int = 200) -> str:
    """Last lines of a text file, or an empty string if it doesn't exist yet."""
    try:
        return "".join(Path(path).read_text(encoding="utf-8").splitlines(keepends=True)[-lines:])
    except FileNotFoundError:
        return ""
