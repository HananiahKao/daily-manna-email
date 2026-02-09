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
import job_dispatcher

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
        # Load dispatcher rules to get configured job names for logging
        rules = job_dispatcher.load_rules(job_dispatcher.DEFAULT_CONFIG_PATH)
        job_names = [rule.name for rule in rules]

        # Hardcoded 10-minute cron daemon - runs continuously and lets dispatcher decide what to execute
        self.scheduler.add_job(
            self._run_dispatcher_trigger,
            CronTrigger(minute="*/10", timezone=sm.TAIWAN_TZ),
            id="dispatcher_trigger",
            name="Job Dispatcher (10min cycle)",
            max_instances=1,
            replace_existing=True
        )

        logger.info(f"Scheduled jobs configured: {', '.join(job_names)}")

    async def _run_dispatcher_trigger(self) -> None:
        """Run the hybrid job dispatcher system."""
        try:
            # Load current configuration
            rules = job_dispatcher.load_rules(job_dispatcher.DEFAULT_CONFIG_PATH)
            state = job_dispatcher.load_state(job_dispatcher.DEFAULT_STATE_PATH)

            # Get current time in Taiwan timezone
            now = dt.datetime.now(tz=sm.TAIWAN_TZ)

            # Max delay for our frequent checking system (30 minutes)
            max_delay = dt.timedelta(minutes=30)

            # Ask dispatcher what jobs should run (decision only)
            jobs_to_run = job_dispatcher.get_jobs_to_run(rules, now, state, max_delay)

            # Execute each job using cron_runner's robust execution system (in parallel)
            executed_jobs = []
            job_tasks = []

            async def job_task_wrapper(rule):
                """Wrap job execution with state tracking."""
                try:
                    # Execute job with full retry logic and tracking
                    await self._execute_job_from_rule(rule)
                    # On successful execution, update dispatch state
                    job_dispatcher.update_job_run_time(state, rule.name, now)
                    executed_jobs.append(rule.name)
                except Exception as e:
                    logger.error(f"Failed to execute job {rule.name}: {e}")
                    # Don't update state for failed jobs - they can retry later

            # Create tasks for each job
            for rule in jobs_to_run:
                task = asyncio.create_task(job_task_wrapper(rule))
                job_tasks.append(task)

            # Wait for all jobs to complete
            await asyncio.gather(*job_tasks, return_exceptions=True)

            # Save updated state after all executions
            if executed_jobs:
                job_dispatcher.save_state(job_dispatcher.DEFAULT_STATE_PATH, state)

            if executed_jobs:
                logger.info(f"Executed jobs: {', '.join(executed_jobs)}")
            else:
                logger.debug("No jobs due at this time")

        except Exception as e:
            logger.error(f"Dispatcher trigger failed: {e}")
            # Don't track dispatcher failures as individual job failures
            # since this is an internal cron mechanism

    async def _execute_job_from_rule(self, rule: job_dispatcher.DispatchRule) -> None:
        """Execute a job from a dispatcher rule with tracking and retry logic.

        Args:
            rule: DispatchRule containing the job information and commands to execute
        """
        # Use the first command from the rule (most jobs have one command)
        if not rule.commands:
            logger.error(f"Job {rule.name} has no commands to execute")
            return

        await self._execute_job_with_retries(
            rule=rule,
            max_retries=3,  # Default retries
            timeout=600  # 10 minutes
        )

    async def _execute_job_with_retries(
        self,
        rule: job_dispatcher.DispatchRule,
        max_retries: int = 3,
        timeout: int = 600
    ) -> None:
        """Execute a job with proper retry loop (no recursion).

        Args:
            rule: DispatchRule containing job information and environment variables
            max_retries: Maximum number of retries
            timeout: Command timeout in seconds
        """
        # Use the first command from the rule (most jobs have one command)
        if not rule.commands:
            logger.error(f"Job {rule.name} has no commands to execute")
            return
            
        command = list(rule.commands[0])
        
        # Create job result once for all attempts - logs will accumulate
        job_result = self.job_tracker.start_job(rule.name, max_retries)

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            attempt_info = f"Attempt {attempt + 1}/{max_retries + 1}" if attempt > 0 else None
            try:
                await self._execute_job_single_attempt(
                    command=command,
                    timeout=timeout,
                    attempt_info=attempt_info,
                    job_result=job_result,
                    rule=rule
                )
                return  # Success - exit retry loop
            except Exception as e:
                if attempt < max_retries:
                    logger.info(f"Job {rule.name} failed ({attempt_info or 'initial'}), retrying in 60 seconds")
                    await asyncio.sleep(60)  # Wait 1 minute before retry
                else:
                    logger.error(f"Job {rule.name} failed permanently after {max_retries + 1} attempts")
                    # Set final status to failed when all retries are exhausted
                    self.job_tracker.update_job(job_result, status="failed")
                    raise  # Re-raise the last exception

    async def _execute_job_single_attempt(
        self,
        command: List[str],
        timeout: int = 600,
        attempt_info: Optional[str] = None,
        job_result: Optional[JobExecutionResult] = None,
        rule: Optional[job_dispatcher.DispatchRule] = None,
        job_name: Optional[str] = None
    ) -> None:
        """Execute a single job attempt without retries.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            attempt_info: Optional retry attempt marker (e.g., "Attempt 2/4")
            job_result: Existing JobExecutionResult to accumulate logs into (for retries)
            rule: DispatchRule containing job information (when job_result is None)
            job_name: Job name for single attempts (when both job_result and rule are None)

        Raises:
            Exception: If the job execution fails
        """
        if job_result is not None:
            # Retry scenario: use existing job result
            job_name = job_result.job_name
        elif rule is not None:
            # Single attempt scenario: create new job result using rule
            job_name = rule.name
            job_result = self.job_tracker.start_job(job_name, 0)
        elif job_name is not None:
            # Backward compatibility: create new job result using job_name
            job_result = self.job_tracker.start_job(job_name, 0)
        else:
            raise ValueError("Either job_result, rule, or job_name must be provided")

        try:
            logger.info(f"Starting job: {job_name}")
            if attempt_info:
                job_result.logs.append("")
                job_result.logs.append(f"=== {attempt_info} ===")
                job_result.logs.append("")
            job_result.logs.append(f"Starting job: {job_name}")
            job_result.logs.append(f"Command: {' '.join(command)}")

            # Execute the command with job-specific environment variables
            job_env = self._get_job_env_vars(rule) if rule and hasattr(rule, 'env') else self._get_env_vars()
            
            # Log environment variables for debugging
            if job_env:
                logger.info(f"Job {job_name} using environment variables: {list(job_env.keys())}")
                job_result.logs.append(f"Environment variables: {list(job_env.keys())}")
            
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **job_env},
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
                else:
                    error_msg = f"Command failed with exit code {exit_code}"
                    job_result.error_message = error_msg
                    job_result.logs.append(error_msg)
                    logger.error(f"Job {job_name} failed: {error_msg}")
                    # Set status to failed only for single attempts (no retries)
                    update_kwargs = {
                        "exit_code": exit_code,
                        "json_output": json_output,
                        "metadata": {
                            "command": command,
                            "timeout": timeout,
                            "stdout_length": len(stdout_text),
                            "stderr_length": len(stderr_text)
                        }
                    }
                    if job_result.max_retries == 0:
                        update_kwargs["status"] = "failed"
                    self.job_tracker.update_job(job_result, **update_kwargs)
                    raise Exception(error_msg)  # Raise exception to trigger retry

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                error_msg = f"Job {job_name} timed out after {timeout} seconds"
                logger.error(error_msg)
                job_result.error_message = error_msg
                job_result.logs.append(error_msg)
                # Set status to failed only for single attempts (no retries)
                update_kwargs = {
                    "error_message": error_msg,
                    "logs": [error_msg]
                }
                if job_result.max_retries == 0:
                    update_kwargs["status"] = "failed"
                self.job_tracker.update_job(job_result, **update_kwargs)
                raise Exception(error_msg)  # Raise exception to trigger retry

        except Exception as e:
            error_msg = f"Job {job_name} failed with exception: {str(e)}"
            logger.error(error_msg)
            if not job_result.error_message:  # Don't overwrite existing error
                job_result.error_message = error_msg
                job_result.logs.append(error_msg)
                # Set status to failed only for single attempts (no retries)
                update_kwargs = {
                    "error_message": error_msg,
                    "logs": [error_msg]
                }
                if job_result.max_retries == 0:
                    update_kwargs["status"] = "failed"
                self.job_tracker.update_job(job_result, **update_kwargs)
            raise  # Re-raise to trigger retry





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

    def _get_job_env_vars(self, job_rule: job_dispatcher.DispatchRule) -> Dict[str, str]:
        """Get combined environment variables for a specific job.
        
        Combines global environment variables from .env file with job-specific
        environment variables, with job-specific variables taking precedence.
        
        Args:
            job_rule: The DispatchRule for the job
            
        Returns:
            Combined environment variables dictionary
        """
        # Start with global environment variables
        env_vars = self._get_env_vars()
        
        # Add job-specific environment variables if they exist
        if job_rule.env:
            env_vars.update(job_rule.env)
            
        return env_vars

    async def run_job_manually(self, job_name: str) -> Optional[JobExecutionResult]:
        """Manually trigger a job execution.

        Args:
            job_name: Name of the job to run

        Returns:
            JobExecutionResult if job exists, None otherwise
        """
        # Load dispatcher rules to find the requested job
        rules = job_dispatcher.load_rules(job_dispatcher.DEFAULT_CONFIG_PATH)
        rule = next((r for r in rules if r.name == job_name), None)

        if not rule:
            logger.warning(f"Unknown job name: {job_name}")
            return None

        # Execute the job's commands manually with tracking
        await self._execute_job_from_rule(rule)
        return self.job_tracker.get_recent_executions(job_name, limit=1)[0] if self.job_tracker.get_recent_executions(job_name, limit=1) else None

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
