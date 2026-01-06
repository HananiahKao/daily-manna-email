"""Job execution tracking and history management for the web app."""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import schedule_manager as sm


@dataclass
class JobExecutionResult:
    """Represents the result of a job execution."""

    job_name: str
    start_time: dt.datetime
    end_time: Optional[dt.datetime] = None
    status: str = "running"  # running, success, failed, skipped
    exit_code: Optional[int] = None
    json_output: Optional[Dict[str, Any]] = None
    logs: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def is_success(self) -> bool:
        """Check if the job execution was successful."""
        return self.status == "success"

    @property
    def is_failed(self) -> bool:
        """Check if the job execution failed."""
        return self.status == "failed"

    @property
    def is_running(self) -> bool:
        """Check if the job is currently running."""
        return self.status == "running"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "job_name": self.job_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "exit_code": self.exit_code,
            "json_output": self.json_output,
            "logs": self.logs,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JobExecutionResult:
        """Create from dictionary (for JSON deserialization)."""
        start_time = dt.datetime.fromisoformat(data["start_time"])
        end_time = dt.datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None

        return cls(
            job_name=data["job_name"],
            start_time=start_time,
            end_time=end_time,
            status=data["status"],
            exit_code=data["exit_code"],
            json_output=data["json_output"],
            logs=data["logs"],
            retry_count=data["retry_count"],
            max_retries=data["max_retries"],
            error_message=data["error_message"],
            metadata=data["metadata"],
        )


class JobTracker:
    """Tracks job executions and provides history management."""

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize the job tracker.

        Args:
            storage_path: Path to store job execution history. Defaults to state/job_history.json
        """
        if storage_path is None:
            # Default to state directory
            project_root = Path(__file__).resolve().parents[1]
            storage_path = project_root / "state" / "job_history.json"

        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_jobs: Dict[str, JobExecutionResult] = {}
        self._load_history()

    def _load_history(self) -> None:
        """Load job execution history from storage."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for job_data in data.get("executions", []):
                job = JobExecutionResult.from_dict(job_data)
                # Only keep recent jobs (last 30 days)
                if job.start_time > dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(days=30):
                    key = f"{job.job_name}_{job.start_time.isoformat()}"
                    self._current_jobs[key] = job
        except (json.JSONDecodeError, KeyError, ValueError):
            # If file is corrupted, start fresh
            pass

    def _save_history(self) -> None:
        """Save job execution history to storage."""
        data = {
            "last_updated": dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat(),
            "executions": [job.to_dict() for job in self._current_jobs.values()]
        }

        # Write to temporary file first, then replace
        temp_path = self.storage_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        temp_path.replace(self.storage_path)

    def start_job(self, job_name: str, max_retries: int = 3) -> JobExecutionResult:
        """Start tracking a new job execution.

        Args:
            job_name: Name of the job
            max_retries: Maximum number of retries allowed

        Returns:
            JobExecutionResult instance for tracking the job
        """
        start_time = dt.datetime.now(tz=sm.TAIWAN_TZ)
        job = JobExecutionResult(
            job_name=job_name,
            start_time=start_time,
            max_retries=max_retries
        )

        key = f"{job_name}_{start_time.isoformat()}"
        self._current_jobs[key] = job
        self._save_history()

        return job

    def update_job(
        self,
        job: JobExecutionResult,
        status: Optional[str] = None,
        exit_code: Optional[int] = None,
        json_output: Optional[Dict[str, Any]] = None,
        logs: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update job execution details.

        Args:
            job: The job to update
            status: New status (running, success, failed, skipped)
            exit_code: Process exit code
            json_output: Structured JSON output from the job
            logs: Additional log lines
            error_message: Error message if failed
            metadata: Additional metadata
        """
        if status:
            job.status = status
            if status in ("success", "failed", "skipped"):
                job.end_time = dt.datetime.now(tz=sm.TAIWAN_TZ)

        if exit_code is not None:
            job.exit_code = exit_code

        if json_output:
            job.json_output = json_output

        if logs:
            job.logs.extend(logs)

        if error_message:
            job.error_message = error_message

        if metadata:
            job.metadata.update(metadata)

        self._save_history()

    def retry_job(self, job: JobExecutionResult) -> bool:
        """Mark a job for retry if retries are available.

        Args:
            job: The job to retry

        Returns:
            True if retry was allowed, False if max retries exceeded
        """
        if job.retry_count >= job.max_retries:
            return False

        job.retry_count += 1
        job.status = "running"
        job.start_time = dt.datetime.now(tz=sm.TAIWAN_TZ)
        job.end_time = None
        job.error_message = None

        self._save_history()
        return True

    def get_recent_executions(self, job_name: Optional[str] = None, limit: int = 50) -> List[JobExecutionResult]:
        """Get recent job executions.

        Args:
            job_name: Filter by job name (optional)
            limit: Maximum number of executions to return

        Returns:
            List of recent job executions, most recent first
        """
        jobs = list(self._current_jobs.values())

        if job_name:
            jobs = [j for j in jobs if j.job_name == job_name]

        # Sort by start time, most recent first
        jobs.sort(key=lambda j: j.start_time, reverse=True)

        return jobs[:limit]

    def get_job_stats(self, job_name: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for job executions.

        Args:
            job_name: Filter by job name (optional)

        Returns:
            Dictionary with job statistics
        """
        jobs = self.get_recent_executions(job_name, limit=1000)  # Get more for stats

        if not jobs:
            return {
                "total_runs": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "last_run": None,
                "status_counts": {}
            }

        total_runs = len(jobs)
        successful_runs = len([j for j in jobs if j.is_success])
        success_rate = successful_runs / total_runs if total_runs > 0 else 0.0

        durations = [j.duration_seconds for j in jobs if j.duration_seconds is not None]
        average_duration = sum(durations) / len(durations) if durations else 0.0

        status_counts = {}
        for job in jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1

        last_run = max(jobs, key=lambda j: j.start_time) if jobs else None

        return {
            "total_runs": total_runs,
            "success_rate": success_rate,
            "average_duration": average_duration,
            "last_run": last_run.start_time.isoformat() if last_run else None,
            "status_counts": status_counts
        }


# Global job tracker instance
_job_tracker: Optional[JobTracker] = None


def get_job_tracker() -> JobTracker:
    """Get the global job tracker instance."""
    global _job_tracker
    if _job_tracker is None:
        _job_tracker = JobTracker()
    return _job_tracker
