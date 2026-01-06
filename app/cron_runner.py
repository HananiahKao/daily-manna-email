"""Background cron job runner using APScheduler integrated with the web app."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import schedule_manager as sm

from app.job_tracker import get_job_tracker, JobExecutionResult


logger = logging.getLogger(__name__)


class CronJobRunner:
    """Manages background cron jobs using APScheduler."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.job_tracker = get_job_tracker()
        self.project_root = Path(__file__).resolve().parents[1]
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Set up logging for the cron runner."""
        # Create logs directory if it doesn't exist
        log_dir = self.project_root / "logs"
        log_dir.mkdir(exist_ok=True)

        # Set up file handler for cron jobs
        log_file = log_dir / "cron_jobs.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s %(name)s %(levelname)s: %(message)s'
            )
        )
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)

    async def start(self) -> None:
        """Start the scheduler."""
        logger.info("Starting cron job scheduler")
        self._setup_jobs()
        self.scheduler.start()
        logger.info("Cron job scheduler started")

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        logger.info("Shutting down cron job scheduler")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        logger.info("Cron job scheduler shut down")

    def _setup_jobs(self) -> None:
        """Set up the scheduled jobs."""
        # Daily email send job (6:00 AM Taiwan time)
        self.scheduler.add_job(
            self._run_daily_email_job,
            CronTrigger(hour=6, minute=0, timezone=sm.TAIWAN_TZ),
            id="daily_email_send",
            name="Daily Email Send",
            max_instances=1,
            replace_existing=True
        )

        # Weekly schedule summary job (9:00 PM Sunday Taiwan time)
        self.scheduler.add_job(
            self._run_weekly_summary_job,
            CronTrigger(day_of_week=6, hour=21, minute=0, timezone=sm.TAIWAN_TZ),
            id="weekly_schedule_summary",
            name="Weekly Schedule Summary",
            max_instances=1,
            replace_existing=True
        )

        logger.info("Scheduled jobs configured: daily_email_send, weekly_schedule_summary")

    async def _run_daily_email_job(self) -> None:
        """Run the daily email send job."""
        await self._execute_job(
            job_name="daily_email_send",
            command=[str(self.project_root / "scripts" / "run_daily_stateful_ezoe.sh")],
            max_retries=3
        )

    async def _run_weekly_summary_job(self) -> None:
        """Run the weekly schedule summary job."""
        await self._execute_job(
            job_name="weekly_schedule_summary",
            command=[str(self.project_root / "scripts" / "run_weekly_schedule_summary.sh")],
            max_retries=2
        )

    async def _execute_job(
        self,
        job_name: str,
        command: List[str],
        max_retries: int = 3,
        timeout: int = 600  # 10 minutes timeout
    ) -> None:
        """Execute a job command with tracking and retry logic.

        Args:
            job_name: Name of the job for tracking
            command: Command to execute
            max_retries: Maximum number of retries
            timeout: Command timeout in seconds
        """
        job_result = self.job_tracker.start_job(job_name, max_retries)

        try:
            logger.info(f"Starting job: {job_name}")
            job_result.logs.append(f"Starting job: {job_name}")
            job_result.logs.append(f"Command: {' '.join(command)}")

            # Execute the command
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self._get_env_vars()},
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                exit_code = process.returncode
                stdout_text = stdout.decode('utf-8', errors='replace').strip()
                stderr_text = stderr.decode('utf-8', errors='replace').strip()

                # Store logs
                if stdout_text:
                    job_result.logs.extend(stdout_text.split('\n'))
                if stderr_text:
                    job_result.logs.extend(stderr_text.split('\n'))

                # Try to parse JSON output from stdout
                json_output = self._extract_json_output(stdout_text)

                # Update job result
                if exit_code == 0:
                    status = "success"
                    logger.info(f"Job {job_name} completed successfully")
                else:
                    status = "failed"
                    error_msg = f"Command failed with exit code {exit_code}"
                    job_result.error_message = error_msg
                    job_result.logs.append(error_msg)
                    logger.error(f"Job {job_name} failed: {error_msg}")

                self.job_tracker.update_job(
                    job_result,
                    status=status,
                    exit_code=exit_code,
                    json_output=json_output,
                    metadata={
                        "command": command,
                        "timeout": timeout,
                        "stdout_length": len(stdout_text),
                        "stderr_length": len(stderr_text)
                    }
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                error_msg = f"Job {job_name} timed out after {timeout} seconds"
                logger.error(error_msg)
                self.job_tracker.update_job(
                    job_result,
                    status="failed",
                    error_message=error_msg,
                    logs=[error_msg]
                )

        except Exception as e:
            error_msg = f"Job {job_name} failed with exception: {str(e)}"
            logger.error(error_msg)
            self.job_tracker.update_job(
                job_result,
                status="failed",
                error_message=error_msg,
                logs=[error_msg]
            )

        # Handle retries if job failed
        if job_result.is_failed and job_result.retry_count < job_result.max_retries:
            if self.job_tracker.retry_job(job_result):
                logger.info(f"Retrying job {job_name} (attempt {job_result.retry_count + 1}/{job_result.max_retries + 1})")
                # Schedule retry after a delay
                await asyncio.sleep(60)  # Wait 1 minute before retry
                await self._execute_job(job_name, command, max_retries, timeout)

    def _extract_json_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Extract JSON output from command stdout.

        Args:
            output: Raw command output

        Returns:
            Parsed JSON object if found, None otherwise
        """
        lines = output.strip().split('\n')
        for line in reversed(lines):  # Check from the end first
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def _get_env_vars(self) -> Dict[str, str]:
        """Get environment variables for job execution."""
        env = {}

        # Load .env file if it exists
        env_file = self.project_root / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            key, _, value = line.partition('=')
                            if key and value:
                                env[key.strip()] = value.strip()
            except Exception:
                pass  # Ignore env file errors

        return env

    async def run_job_manually(self, job_name: str) -> Optional[JobExecutionResult]:
        """Manually trigger a job execution.

        Args:
            job_name: Name of the job to run

        Returns:
            JobExecutionResult if job exists, None otherwise
        """
        if job_name == "daily_email_send":
            await self._run_daily_email_job()
            return self.job_tracker.get_recent_executions(job_name, limit=1)[0] if self.job_tracker.get_recent_executions(job_name, limit=1) else None
        elif job_name == "weekly_schedule_summary":
            await self._run_weekly_summary_job()
            return self.job_tracker.get_recent_executions(job_name, limit=1)[0] if self.job_tracker.get_recent_executions(job_name, limit=1) else None

        logger.warning(f"Unknown job name: {job_name}")
        return None

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get the current status of the scheduler."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "running": self.scheduler.running,
            "jobs": jobs
        }


# Global cron runner instance
_cron_runner: Optional[CronJobRunner] = None


async def get_cron_runner() -> CronJobRunner:
    """Get the global cron runner instance."""
    global _cron_runner
    if _cron_runner is None:
        _cron_runner = CronJobRunner()
        await _cron_runner.start()
    return _cron_runner


async def shutdown_cron_runner() -> None:
    """Shutdown the global cron runner."""
    global _cron_runner
    if _cron_runner:
        await _cron_runner.shutdown()
        _cron_runner = None
