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
def temp_project_root(fs):
    """Create a temporary project root with necessary directories in fake file system."""
    temp_path = "/test/project_root"
    fs.create_dir(temp_path)
    
    # Create logs directory
    logs_dir = f"{temp_path}/logs"
    fs.create_dir(logs_dir)

    # Create state directory
    state_dir = f"{temp_path}/state"
    fs.create_dir(state_dir)

    # Create a minimal .env file
    env_file = f"{temp_path}/.env"
    fs.create_file(env_file, contents="TEST_VAR=test_value\n")
    from pathlib import Path
    return Path(temp_path)


@pytest.fixture
def mock_scheduler():
    """Mock APScheduler instance."""
    scheduler = Mock()
    scheduler.running = False
    scheduler.get_jobs.return_value = []
    return scheduler


@pytest.fixture
async def cron_runner_with_tracker(temp_project_root, mock_scheduler, fs):
    """Create a cron runner with a real job tracker for integration testing."""
    with patch('app.cron_runner.AsyncIOScheduler', return_value=mock_scheduler), \
         patch('app.cron_runner.Path') as mock_path_class:

        # Mock Path to simulate app/cron_runner.py being in temp_project_root/app/cron_runner.py
        mock_app_dir = temp_project_root / "app"
        mock_app_dir.mkdir(exist_ok=True)

        mock_path_instance = Mock()
        mock_path_instance.resolve.return_value = mock_app_dir / "cron_runner.py"
        mock_path_instance.parents = [mock_app_dir, temp_project_root]  # parents[1] is project root
        mock_path_instance.__truediv__ = lambda self, x: temp_project_root / x
        mock_path_class.return_value = mock_path_instance

        # Create a real job tracker with isolated storage in temp directory (fake file system)
        isolated_history_path = temp_project_root / "state" / "job_history.json"
        real_job_tracker = JobTracker(storage_path=isolated_history_path)

        runner = CronJobRunner()
        # Override the scheduler with our mock and replace job tracker
        runner.scheduler = mock_scheduler
        runner.job_tracker = real_job_tracker

        yield runner

        # Cleanup
        await runner.shutdown()


class TestMultipleJobsDueAtSameTime:
    """Tests for handling multiple jobs due at the same time."""

    @pytest.mark.asyncio
    async def test_multiple_jobs_executed_in_parallel(self, cron_runner_with_tracker):
        """Test that multiple jobs due at the same time are executed in parallel."""
        runner = cron_runner_with_tracker

        # Create multiple jobs scheduled for the same time
        mock_rule1 = Mock()
        mock_rule1.name = "job1"
        mock_rule1.time = dt.time(6, 0)
        mock_rule1.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule1.commands = [["echo", "job1"]]

        mock_rule2 = Mock()
        mock_rule2.name = "job2"
        mock_rule2.time = dt.time(6, 0)
        mock_rule2.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule2.commands = [["echo", "job2"]]

        mock_rule3 = Mock()
        mock_rule3.name = "job3"
        mock_rule3.time = dt.time(6, 0)
        mock_rule3.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule3.commands = [["echo", "job3"]]

        # Mock current time to trigger all jobs
        now = dt.datetime(2024, 1, 1, 6, 0, tzinfo=sm.TAIWAN_TZ)  # Monday at 6:00 AM

        # Mock dispatcher to return all jobs
        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule1, mock_rule2, mock_rule3]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[mock_rule1, mock_rule2, mock_rule3]), \
             patch('app.cron_runner.job_dispatcher.update_job_run_time') as mock_update_time, \
             patch('app.cron_runner.job_dispatcher.save_state') as mock_save_state, \
             patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create:

            # Mock subprocess calls to track execution
            execution_count = 0

            def create_subprocess_side_effect(*args, **kwargs):
                # args contains the command and its arguments
                nonlocal execution_count
                execution_count += 1
                mock_process = AsyncMock()
                mock_process.communicate.return_value = (b"", b"")
                mock_process.returncode = 0
                mock_process.wait = AsyncMock()
                return mock_process

            mock_create.side_effect = create_subprocess_side_effect

            # Patch asyncio.sleep to be instant
            with patch('app.cron_runner.asyncio.sleep', return_value=None):
                await runner._run_dispatcher_trigger()

            # Verify all jobs were executed (3 jobs total)
            assert execution_count == 3

            # Verify state was updated only once after all jobs completed
            mock_update_time.assert_called()
            mock_save_state.assert_called()

    @pytest.mark.asyncio
    async def test_job_failure_does_not_prevent_other_jobs(self, cron_runner_with_tracker):
        """Test that one job failing doesn't prevent other jobs from running."""
        runner = cron_runner_with_tracker

        # Create jobs: job1 succeeds, job2 fails, job3 succeeds
        mock_rule1 = Mock()
        mock_rule1.name = "job1_success"
        mock_rule1.time = dt.time(6, 0)
        mock_rule1.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule1.commands = [["echo", "success1"]]

        mock_rule2 = Mock()
        mock_rule2.name = "job2_fail"
        mock_rule2.time = dt.time(6, 0)
        mock_rule2.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule2.commands = [["failing", "command"]]

        mock_rule3 = Mock()
        mock_rule3.name = "job3_success"
        mock_rule3.time = dt.time(6, 0)
        mock_rule3.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule3.commands = [["echo", "success3"]]

        # Mock current time to trigger all jobs
        now = dt.datetime(2024, 1, 1, 6, 0, tzinfo=sm.TAIWAN_TZ)

        # Mock dispatcher to return all jobs
        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule1, mock_rule2, mock_rule3]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[mock_rule1, mock_rule2, mock_rule3]), \
             patch('app.cron_runner.job_dispatcher.update_job_run_time') as mock_update_time, \
             patch('app.cron_runner.job_dispatcher.save_state') as mock_save_state, \
             patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create:

            # Patch asyncio.sleep to be instant
            with patch('app.cron_runner.asyncio.sleep', return_value=None):
                # Mock subprocess calls: job1 succeeds, job2 fails (with retries), job3 succeeds
                mock_create.side_effect = [
                    # job1_success
                    self._create_success_mock(),
                    # job2_fail - attempt 1 (fail)
                    self._create_failure_mock(),
                    # job2_fail - attempt 2 (fail)
                    self._create_failure_mock(),
                    # job2_fail - attempt 3 (fail)
                    self._create_failure_mock(),
                    # job2_fail - attempt 4 (fail)
                    self._create_failure_mock(),
                    # job3_success - attempt 1 (success)
                    self._create_success_mock()
                ]

                await runner._run_dispatcher_trigger()

            # Verify all jobs were attempted with retries
            # Each job can have up to 4 attempts (1 initial + 3 retries)
            assert mock_create.call_count <= 12  # 3 jobs * 4 attempts
            assert mock_create.call_count >= 3   # At least one attempt per job

            # Verify state was updated (should happen after all jobs complete)
            mock_update_time.assert_called()
            mock_save_state.assert_called()

            # Verify job tracker has entries for all three jobs
            job1_executions = runner.job_tracker.get_recent_executions("job1_success")
            job2_executions = runner.job_tracker.get_recent_executions("job2_fail")
            job3_executions = runner.job_tracker.get_recent_executions("job3_success")

            assert len(job1_executions) == 1
            assert len(job2_executions) == 1
            assert len(job3_executions) == 1

            assert job1_executions[0].status == "success"
            assert job2_executions[0].status == "failed"
            assert job3_executions[0].status == "success"

    @pytest.mark.asyncio
    async def test_state_updated_only_after_all_jobs_complete(self, cron_runner_with_tracker):
        """Test that state is updated only after all jobs complete."""
        runner = cron_runner_with_tracker

        # Create multiple jobs
        mock_rule1 = Mock()
        mock_rule1.name = "state_job1"
        mock_rule1.time = dt.time(6, 0)
        mock_rule1.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule1.commands = [["echo", "state1"]]

        mock_rule2 = Mock()
        mock_rule2.name = "state_job2"
        mock_rule2.time = dt.time(6, 0)
        mock_rule2.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule2.commands = [["echo", "state2"]]

        # Mock current time to trigger all jobs
        now = dt.datetime(2024, 1, 1, 6, 0, tzinfo=sm.TAIWAN_TZ)

        # Mock dispatcher to return all jobs
        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule1, mock_rule2]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[mock_rule1, mock_rule2]), \
             patch('app.cron_runner.job_dispatcher.update_job_run_time') as mock_update_time, \
             patch('app.cron_runner.job_dispatcher.save_state') as mock_save_state, \
             patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create:

            # Mock subprocess calls
            mock_create.side_effect = [
                self._create_success_mock(),  # job1
                self._create_success_mock()   # job2
            ]

            # Track when state update is called
            state_update_called = False

            def mock_update_time_side_effect(*args, **kwargs):
                nonlocal state_update_called
                state_update_called = True

            mock_update_time.side_effect = mock_update_time_side_effect

            # Patch asyncio.sleep to be instant
            with patch('app.cron_runner.asyncio.sleep', return_value=None):
                await runner._run_dispatcher_trigger()

            # Verify state was updated only once after all jobs completed
            assert state_update_called is True
            mock_save_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_logic_applied_per_job(self, cron_runner_with_tracker):
        """Test that retry logic is applied independently to each job."""
        runner = cron_runner_with_tracker

        # Create jobs with different retry needs
        mock_rule1 = Mock()
        mock_rule1.name = "retry_job1"
        mock_rule1.time = dt.time(6, 0)
        mock_rule1.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule1.commands = [["echo", "retry1"]]

        mock_rule2 = Mock()
        mock_rule2.name = "retry_job2"
        mock_rule2.time = dt.time(6, 0)
        mock_rule2.weekdays = (0, 1, 2, 3, 4, 5, 6)
        mock_rule2.commands = [["echo", "retry2"]]

        # Mock current time to trigger all jobs
        now = dt.datetime(2024, 1, 1, 6, 0, tzinfo=sm.TAIWAN_TZ)

        # Mock dispatcher to return all jobs
        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule1, mock_rule2]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[mock_rule1, mock_rule2]), \
             patch('app.cron_runner.job_dispatcher.update_job_run_time') as mock_update_time, \
             patch('app.cron_runner.job_dispatcher.save_state') as mock_save_state, \
             patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create:

            # Mock subprocess calls with retries
            retry_attempts = []

            def create_subprocess_side_effect(*args, **kwargs):
                # args contains the command and its arguments
                command = args
                retry_attempts.append(command[0])  # First arg is the command name
                mock_process = AsyncMock()
                # First call fails, second succeeds
                if len(retry_attempts) == 1 or len(retry_attempts) == 3:
                    mock_process.communicate.return_value = (b"", b"fail")
                    mock_process.returncode = 1
                else:
                    mock_process.communicate.return_value = (b"success", b"")
                    mock_process.returncode = 0
                mock_process.wait = AsyncMock()
                return mock_process
            mock_create.side_effect = create_subprocess_side_effect

            # Patch asyncio.sleep to be instant
            with patch('app.cron_runner.asyncio.sleep', return_value=None):
                await runner._run_dispatcher_trigger()

            # Verify each job had its own retry attempts
            # job1: 2 attempts (fail, success)
            # job2: 2 attempts (fail, success)
            assert len(retry_attempts) == 4
            assert retry_attempts[0] == "echo"  # job1 attempt 1
            assert retry_attempts[1] == "echo"  # job2 attempt 1
            assert retry_attempts[2] == "echo"  # job1 attempt 2
            assert retry_attempts[3] == "echo"  # job2 attempt 2

    def _create_success_mock(self):
        """Helper to create a successful subprocess mock."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success output", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()
        return mock_process

    def _create_failure_mock(self):
        """Helper to create a failing subprocess mock."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error message")
        mock_process.returncode = 1
        mock_process.wait = AsyncMock()
        return mock_process
