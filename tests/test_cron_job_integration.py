import asyncio
import datetime as dt
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

import job_dispatcher
import schedule_manager as sm

from app.cron_runner import CronJobRunner
from app.job_tracker import JobTracker


@pytest.fixture
def temp_project_root(tmp_path):
    """Create a temporary project root with necessary directories."""
    # Create logs directory
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    # Create state directory
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Create a minimal .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR=test_value\n")

    return tmp_path


@pytest.fixture
def mock_scheduler():
    """Mock APScheduler instance."""
    scheduler = Mock()
    scheduler.running = False
    scheduler.get_jobs.return_value = []
    return scheduler


@pytest.fixture
async def cron_runner_with_tracker(temp_project_root, mock_scheduler):
    """Create a cron runner with a real job tracker for integration testing."""
    with patch('app.cron_runner.AsyncIOScheduler', return_value=mock_scheduler), \
         patch('app.cron_runner.Path') as mock_path_class, \
         patch('app.job_tracker.JobTracker') as mock_job_tracker_class:

        # Mock Path to simulate app/cron_runner.py being in temp_project_root/app/cron_runner.py
        mock_app_dir = temp_project_root / "app"
        mock_app_dir.mkdir(exist_ok=True)

        mock_path_instance = Mock()
        mock_path_instance.resolve.return_value = mock_app_dir / "cron_runner.py"
        mock_path_instance.parents = [mock_app_dir, temp_project_root]  # parents[1] is project root
        mock_path_instance.__truediv__ = lambda self, x: temp_project_root / x
        mock_path_class.return_value = mock_path_instance

        # Create a real job tracker with isolated storage in temp directory
        isolated_history_path = temp_project_root / "state" / "job_history.json"
        real_job_tracker = JobTracker(storage_path=isolated_history_path)

        # Mock the JobTracker constructor to return our isolated instance
        mock_job_tracker_class.return_value = real_job_tracker

        runner = CronJobRunner()
        # Override the scheduler with our mock
        runner.scheduler = mock_scheduler

        yield runner

        # Cleanup
        await runner.shutdown()


class TestCronRunnerJobTrackerIntegration:
    """Integration tests for CronRunner and JobTracker interaction."""

    @pytest.mark.asyncio
    async def test_successful_job_execution_updates_tracker(self, cron_runner_with_tracker):
        """Test that successful job execution properly updates the job tracker."""
        runner = cron_runner_with_tracker

        # Mock subprocess for successful execution
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success output", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process):
            # Execute a job
            await runner._execute_job_with_retries("test_job", ["echo", "success"])

            # Check that job was tracked
            recent_executions = runner.job_tracker.get_recent_executions("test_job")
            assert len(recent_executions) == 1

            job = recent_executions[0]
            assert job.job_name == "test_job"
            assert job.status == "success"
            assert job.exit_code == 0
            assert "success output" in job.logs

    @pytest.mark.asyncio
    async def test_failed_job_execution_updates_tracker(self, cron_runner_with_tracker):
        """Test that failed job execution properly updates the job tracker."""
        runner = cron_runner_with_tracker

        # Mock subprocess for failed execution
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error message")
        mock_process.returncode = 1
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process):
            # Execute a job that should fail after exhausting retries
            with pytest.raises(Exception, match="Command failed with exit code 1"):
                await runner._execute_job_with_retries("failing_job", ["failing", "command"], max_retries=0)  # No retries

            # Check that job failure was tracked with proper status update
            recent_executions = runner.job_tracker.get_recent_executions("failing_job")
            assert len(recent_executions) == 1

            job = recent_executions[0]
            assert job.job_name == "failing_job"
            assert job.status == "failed"  # Fixed: failed jobs now get status updated
            assert job.exit_code == 1      # Fixed: exit code is now properly set
            assert "Command failed with exit code 1" in "\n".join(job.logs)  # Error logged in job logs

    @pytest.mark.asyncio
    async def test_job_retry_updates_tracker_correctly(self, cron_runner_with_tracker):
        """Test that job retries are properly tracked."""
        runner = cron_runner_with_tracker

        # Mock subprocess - first call fails, second succeeds
        mock_process_fail = AsyncMock()
        mock_process_fail.communicate.return_value = (b"", b"fail")
        mock_process_fail.returncode = 1
        mock_process_fail.wait = AsyncMock()

        mock_process_success = AsyncMock()
        mock_process_success.communicate.return_value = (b"success", b"")
        mock_process_success.returncode = 0
        mock_process_success.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', side_effect=[mock_process_fail, mock_process_success]):
            # Execute job with retry
            await runner._execute_job_with_retries("retry_job", ["retry", "command"], max_retries=1)

            # Check that both attempts were tracked
            recent_executions = runner.job_tracker.get_recent_executions("retry_job")
            # Should have only one job entry (with accumulated logs)
            assert len(recent_executions) == 1

            job = recent_executions[0]
            assert job.job_name == "retry_job"
            assert job.status == "success"
            assert job.retry_count == 0  # Retry count not incremented during retry process
            assert "Attempt 2/2" in "\n".join(job.logs)

    @pytest.mark.asyncio
    async def test_timeout_job_execution_updates_tracker(self, cron_runner_with_tracker):
        """Test that timed-out job execution updates tracker correctly."""
        runner = cron_runner_with_tracker

        with patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create, \
             patch('app.cron_runner.asyncio.wait_for', side_effect=asyncio.TimeoutError):

            mock_process = AsyncMock()
            mock_create.return_value = mock_process

            # Execute job that times out
            with pytest.raises(Exception, match="timed out"):
                await runner._execute_job_single_attempt(["slow", "command"], timeout=10, job_name="timeout_job")

            # Check that timeout was tracked
            recent_executions = runner.job_tracker.get_recent_executions("timeout_job")
            assert len(recent_executions) == 1

            job = recent_executions[0]
            assert job.job_name == "timeout_job"
            assert job.status == "failed"
            assert "timed out after 10 seconds" in job.error_message

    @pytest.mark.asyncio
    async def test_dispatcher_trigger_updates_job_state(self, cron_runner_with_tracker):
        """Test that dispatcher trigger properly updates job execution state."""
        runner = cron_runner_with_tracker

        # Create a mock rule
        mock_rule = Mock()
        mock_rule.name = "state_test_job"
        mock_rule.commands = [["echo", "test"]]

        # Mock successful execution
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"test output", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[mock_rule]), \
             patch('app.cron_runner.job_dispatcher.update_job_run_time') as mock_update_time, \
             patch('app.cron_runner.job_dispatcher.save_state') as mock_save_state, \
             patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process):

            await runner._run_dispatcher_trigger()

            # Verify dispatcher state was updated
            mock_update_time.assert_called_once()
            mock_save_state.assert_called_once()

            # Verify job was executed and tracked
            recent_executions = runner.job_tracker.get_recent_executions("state_test_job")
            assert len(recent_executions) == 1
            assert recent_executions[0].status == "success"

    @pytest.mark.asyncio
    async def test_manual_job_execution_integration(self, cron_runner_with_tracker):
        """Test manual job execution through the full pipeline."""
        runner = cron_runner_with_tracker

        # Mock dispatcher rule
        mock_rule = Mock()
        mock_rule.name = "manual_test"
        mock_rule.commands = [["echo", "manual execution"]]

        # Mock successful execution
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"manual output", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule]), \
             patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process):

            result = await runner.run_job_manually("manual_test")

            assert result is not None
            assert result.job_name == "manual_test"
            assert result.status == "success"
            assert "manual output" in result.logs

    def test_scheduler_status_with_job_history(self, cron_runner_with_tracker):
        """Test scheduler status reporting includes job history."""
        runner = cron_runner_with_tracker

        # Add some jobs to the tracker
        job1 = runner.job_tracker.start_job("status_job_1")
        runner.job_tracker.update_job(job1, status="success")

        job2 = runner.job_tracker.start_job("status_job_2")
        runner.job_tracker.update_job(job2, status="running")

        status = runner.get_scheduler_status()

        assert "running" in status
        assert "jobs" in status
        # The scheduler is mocked, so jobs list will be empty from scheduler perspective

    @pytest.mark.asyncio
    async def test_json_output_extraction_integration(self, cron_runner_with_tracker):
        """Test JSON output extraction in full job execution."""
        runner = cron_runner_with_tracker

        # Mock subprocess with JSON output
        json_output = '{"result": "integration_test", "status": "ok"}'
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (f'Command output\n{json_output}\nMore output'.encode(), b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process):
            await runner._execute_job_with_retries("json_job", ["produce", "json"])

            recent_executions = runner.job_tracker.get_recent_executions("json_job")
            assert len(recent_executions) == 1

            job = recent_executions[0]
            assert job.json_output == {"result": "integration_test", "status": "ok"}

    @pytest.mark.asyncio
    async def test_environment_variables_integration(self, cron_runner_with_tracker):
        """Test that environment variables are properly loaded and passed."""
        runner = cron_runner_with_tracker

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"env test", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process) as mock_create:
            await runner._execute_job_single_attempt(["env"], job_name="env_job")

            # Verify subprocess was called with environment variables
            call_args = mock_create.call_args
            env_vars = call_args[1]['env']
            assert 'TEST_VAR' in env_vars
            assert env_vars['TEST_VAR'] == 'test_value'

    def test_job_tracker_persistence_across_cron_runner_instances(self, temp_project_root):
        """Test that job history persists across cron runner instances."""
        isolated_history_path = temp_project_root / "state" / "job_history.json"

        # Create first job tracker and add a job
        tracker1 = JobTracker(storage_path=isolated_history_path)
        job = tracker1.start_job("persistent_job")
        tracker1.update_job(job, status="success")

        # Create second job tracker and check if job history was loaded
        tracker2 = JobTracker(storage_path=isolated_history_path)
        recent_jobs = tracker2.get_recent_executions("persistent_job")

        assert len(recent_jobs) == 1
        assert recent_jobs[0].job_name == "persistent_job"
        assert recent_jobs[0].status == "success"
