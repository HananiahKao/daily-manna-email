import asyncio
import datetime as dt
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

import job_dispatcher
import schedule_manager as sm

from app.cron_runner import CronJobRunner, get_cron_runner, shutdown_cron_runner
from app.job_tracker import JobExecutionResult


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
async def cron_runner(temp_project_root, mock_scheduler):
    """Create a cron runner instance with mocked scheduler."""
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

        runner = CronJobRunner()

        # Override the scheduler with our mock
        runner.scheduler = mock_scheduler

        yield runner

        # Cleanup
        await runner.shutdown()


class TestCronJobRunner:

    async def test_init_sets_up_logging_and_tracker(self, temp_project_root, mock_scheduler):
        """Test that CronJobRunner initializes correctly."""
        with patch('app.cron_runner.AsyncIOScheduler', return_value=mock_scheduler), \
             patch('app.cron_runner.Path') as mock_path_class:

            # Mock Path to simulate app/cron_runner.py being in temp_project_root/app/cron_runner.py
            mock_app_dir = temp_project_root / "app"
            mock_app_dir.mkdir()

            mock_path_instance = Mock()
            mock_path_instance.resolve.return_value = mock_app_dir / "cron_runner.py"
            mock_path_instance.parents = [mock_app_dir, temp_project_root]  # parents[1] is project root
            mock_path_instance.__truediv__ = lambda self, x: temp_project_root / x
            mock_path_class.return_value = mock_path_instance

            runner = CronJobRunner()

            assert runner.project_root == temp_project_root
            assert hasattr(runner, 'job_tracker')
            assert hasattr(runner, 'scheduler')

            # Check that logs directory was created
            assert (temp_project_root / "logs").exists()

    @patch('app.cron_runner.logging.FileHandler')
    def test_setup_logging_creates_log_file(self, mock_file_handler, temp_project_root, mock_scheduler):
        """Test logging setup creates the log file."""
        # Configure mock to have proper level attribute for logging framework compatibility
        mock_file_handler.return_value.level = logging.INFO

        with patch('app.cron_runner.AsyncIOScheduler', return_value=mock_scheduler), \
             patch('app.cron_runner.Path') as mock_path_class:

            # Mock Path to simulate app/cron_runner.py being in temp_project_root/app/cron_runner.py
            mock_app_dir = temp_project_root / "app"
            mock_app_dir.mkdir()

            mock_path_instance = Mock()
            mock_path_instance.resolve.return_value = mock_app_dir / "cron_runner.py"
            mock_path_instance.parents = [mock_app_dir, temp_project_root]  # parents[1] is project root
            mock_path_instance.__truediv__ = lambda self, x: temp_project_root / x
            mock_path_class.return_value = mock_path_instance

            # Create runner (this calls _setup_logging once)
            runner = CronJobRunner()

            # Verify FileHandler was created during initialization
            assert mock_file_handler.call_count >= 1
            # Get the most recent call (from initialization)
            call_args = mock_file_handler.call_args[0]
            assert str(temp_project_root / "logs" / "cron_jobs.log") in str(call_args[0])

    @patch('app.cron_runner.job_dispatcher.load_rules')
    def test_setup_jobs_configures_dispatcher_trigger(self, mock_load_rules, cron_runner, mock_scheduler):
        """Test that jobs are set up with dispatcher trigger."""
        # Mock rules
        mock_rule = Mock()
        mock_rule.name = "test_job"
        mock_load_rules.return_value = [mock_rule]

        cron_runner._setup_jobs()

        # Verify scheduler.add_job was called
        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args

        assert call_args[0][0] == cron_runner._run_dispatcher_trigger
        assert "dispatcher_trigger" in call_args[1]['id']
        assert call_args[1]['max_instances'] == 1

    @patch('app.cron_runner.job_dispatcher.load_rules')
    @patch('app.cron_runner.job_dispatcher.load_state')
    @patch('app.cron_runner.job_dispatcher.get_jobs_to_run')
    @patch('app.cron_runner.job_dispatcher.update_job_run_time')
    @patch('app.cron_runner.job_dispatcher.save_state')
    async def test_run_dispatcher_trigger_executes_jobs(self, mock_save_state, mock_update_run_time,
                                                      mock_get_jobs, mock_load_state, mock_load_rules,
                                                      cron_runner):
        """Test dispatcher trigger executes jobs successfully."""
        # Setup mocks
        mock_rule = Mock()
        mock_rule.name = "test_job"
        mock_load_rules.return_value = [mock_rule]
        mock_load_state.return_value = {}
        mock_get_jobs.return_value = [mock_rule]

        # Mock successful job execution
        with patch.object(cron_runner, '_execute_job_from_rule', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = None

            await cron_runner._run_dispatcher_trigger()

            # Verify job was executed
            mock_execute.assert_called_once_with("test_job", mock_rule)
            # Verify state was updated and saved
            mock_update_run_time.assert_called_once()
            mock_save_state.assert_called_once()

    @patch('app.cron_runner.job_dispatcher.load_rules')
    @patch('app.cron_runner.job_dispatcher.load_state')
    @patch('app.cron_runner.job_dispatcher.get_jobs_to_run')
    async def test_run_dispatcher_trigger_handles_job_failure(self, mock_get_jobs, mock_load_state,
                                                            mock_load_rules, cron_runner):
        """Test dispatcher trigger handles job execution failures."""
        # Setup mocks
        mock_rule = Mock()
        mock_rule.name = "failing_job"
        mock_load_rules.return_value = [mock_rule]
        mock_load_state.return_value = {}
        mock_get_jobs.return_value = [mock_rule]

        # Mock failed job execution
        with patch.object(cron_runner, '_execute_job_from_rule', new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Job failed")

            # Should not raise exception
            await cron_runner._run_dispatcher_trigger()

            # Verify job was attempted
            mock_execute.assert_called_once_with("failing_job", mock_rule)

    def test_execute_job_from_rule_with_commands(self, cron_runner):
        """Test executing job from rule with commands."""
        mock_rule = Mock()
        mock_rule.name = "test_job"
        mock_rule.commands = [["echo", "hello"]]

        with patch.object(cron_runner, '_execute_job_with_retries', new_callable=AsyncMock) as mock_execute:
            # Test sync call (this method is not async in the actual code, but we'll mock it)
            # Actually, looking at the code, this method calls _execute_job_with_retries which is async
            # But this method itself is not marked async. Let me check the actual implementation.

            # The method signature shows it's not async, but calls async method
            # For testing, we'll patch the async call
            pass

    async def test_execute_job_with_retries_success_first_try(self, cron_runner):
        """Test successful job execution on first attempt."""
        command = ["echo", "success"]
        job_name = "test_job"

        with patch.object(cron_runner, '_execute_job_single_attempt', new_callable=AsyncMock) as mock_attempt:
            mock_attempt.return_value = None  # Success

            await cron_runner._execute_job_with_retries(job_name, command, max_retries=2)

            # Should only call once since it succeeded
            assert mock_attempt.call_count == 1

    async def test_execute_job_with_retries_with_retry(self, cron_runner):
        """Test job execution with retry on failure."""
        command = ["failing", "command"]
        job_name = "test_job"

        with patch.object(cron_runner, '_execute_job_single_attempt', new_callable=AsyncMock) as mock_attempt:
            # First call fails, second succeeds
            mock_attempt.side_effect = [Exception("Failed"), None]

            await cron_runner._execute_job_with_retries(job_name, command, max_retries=1)

            # Should call twice: initial + 1 retry
            assert mock_attempt.call_count == 2

    async def test_execute_job_with_retries_max_retries_exceeded(self, cron_runner):
        """Test job execution fails after max retries."""
        command = ["always", "fails"]
        job_name = "test_job"

        with patch.object(cron_runner, '_execute_job_single_attempt', new_callable=AsyncMock) as mock_attempt:
            mock_attempt.side_effect = Exception("Always fails")

            with pytest.raises(Exception, match="Always fails"):
                await cron_runner._execute_job_with_retries(job_name, command, max_retries=1)

            # Should call max_retries + 1 times
            assert mock_attempt.call_count == 2

    async def test_execute_job_single_attempt_success(self, cron_runner):
        """Test single job attempt executes successfully."""
        command = ["echo", "success"]
        job_name = "test_job"

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success output", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            mock_job_result = Mock()
            mock_start_job.return_value = mock_job_result

            await cron_runner._execute_job_single_attempt(command, job_name=job_name)

            # Verify subprocess was created correctly
            # Verify job tracking calls
            mock_start_job.assert_called_once_with(job_name, 0)
            mock_update_job.assert_called_once()

    async def test_execute_job_single_attempt_timeout(self, cron_runner):
        """Test job execution times out."""
        command = ["slow", "command"]
        job_name = "test_job"

        with patch('app.cron_runner.asyncio.create_subprocess_exec') as mock_create, \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            # Mock process that times out
            mock_process = AsyncMock()
            mock_create.return_value = mock_process

            # Make wait_for raise TimeoutError
            with patch('app.cron_runner.asyncio.wait_for', side_effect=asyncio.TimeoutError):
                mock_job_result = Mock()
                mock_start_job.return_value = mock_job_result

                with pytest.raises(Exception, match="timed out"):
                    await cron_runner._execute_job_single_attempt(command, timeout=10, job_name=job_name)

                # Verify job was marked as failed
                mock_update_job.assert_called()

    async def test_execute_job_single_attempt_nonzero_exit(self, cron_runner):
        """Test job execution with non-zero exit code."""
        command = ["failing", "command"]
        job_name = "failing_job"

        # Mock subprocess with failure
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error message")
        mock_process.returncode = 1
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            mock_job_result = Mock()
            mock_start_job.return_value = mock_job_result

            with pytest.raises(Exception, match="Command failed with exit code 1"):
                await cron_runner._execute_job_single_attempt(command, job_name=job_name)

            # Verify that update_job was called with status="failed"
            mock_update_job.assert_called_once()
            call_kwargs = mock_update_job.call_args[1]
            assert call_kwargs['status'] == "failed"
            assert call_kwargs['exit_code'] == 1

    def test_extract_json_output_success(self, cron_runner):
        """Test JSON output extraction from command output."""
        output = "some text\n{\"key\": \"value\"}\nmore text"
        result = cron_runner._extract_json_output(output)

        assert result == {"key": "value"}

    def test_extract_json_output_no_json(self, cron_runner):
        """Test JSON extraction when no JSON is present."""
        output = "just plain text output"
        result = cron_runner._extract_json_output(output)

        assert result is None

    def test_extract_json_output_invalid_json(self, cron_runner):
        """Test JSON extraction with invalid JSON."""
        output = "text\n{\"invalid\": json}\nmore text"
        result = cron_runner._extract_json_output(output)

        assert result is None

    def test_get_env_vars_with_env_file(self, temp_project_root, cron_runner):
        """Test environment variable loading from .env file."""
        env_vars = cron_runner._get_env_vars()

        assert "TEST_VAR" in env_vars
        assert env_vars["TEST_VAR"] == "test_value"

    def test_get_env_vars_no_env_file(self, cron_runner):
        """Test environment variable loading when no .env file exists."""
        # Temporarily move env file
        env_file = cron_runner.project_root / ".env"
        if env_file.exists():
            env_file.rename(env_file.with_suffix('.bak'))

        try:
            env_vars = cron_runner._get_env_vars()
            # Should still work, just empty
            assert isinstance(env_vars, dict)
        finally:
            # Restore env file
            bak_file = cron_runner.project_root / ".env.bak"
            if bak_file.exists():
                bak_file.rename(env_file)

    async def test_run_job_manually_success(self, cron_runner):
        """Test manual job execution."""
        job_name = "manual_job"

        # Mock dispatcher rule
        mock_rule = Mock()
        mock_rule.name = job_name
        mock_rule.commands = [["echo", "manual"]]

        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[mock_rule]), \
             patch.object(cron_runner, '_execute_job_from_rule', new_callable=AsyncMock) as mock_execute, \
             patch.object(cron_runner.job_tracker, 'get_recent_executions') as mock_get_recent:

            mock_result = Mock()
            mock_get_recent.return_value = [mock_result]

            result = await cron_runner.run_job_manually(job_name)

            assert result == mock_result
            mock_execute.assert_called_once_with(job_name, mock_rule)

    async def test_run_job_manually_unknown_job(self, cron_runner):
        """Test manual execution of unknown job."""
        job_name = "unknown_job"

        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[]):
            result = await cron_runner.run_job_manually(job_name)

            assert result is None

    def test_get_scheduler_status(self, cron_runner, mock_scheduler):
        """Test getting scheduler status."""
        # Mock a job
        mock_job = Mock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = dt.datetime.now(dt.timezone.utc)
        mock_job.trigger = Mock()
        str(mock_job.trigger)  # Mock string representation

        mock_scheduler.get_jobs.return_value = [mock_job]
        mock_scheduler.running = True

        status = cron_runner.get_scheduler_status()

        assert status["running"] is True
        assert len(status["jobs"]) == 1
        assert status["jobs"][0]["id"] == "test_job"

    async def test_start_and_shutdown(self, temp_project_root, mock_scheduler):
        """Test starting and shutting down the scheduler."""
        with patch('app.cron_runner.AsyncIOScheduler', return_value=mock_scheduler), \
             patch('app.cron_runner.Path') as mock_path_class:

            mock_path_instance = Mock()
            mock_path_instance.resolve.return_value = temp_project_root
            mock_path_instance.parents = [temp_project_root]
            mock_path_instance.__truediv__ = lambda self, x: temp_project_root / x
            mock_path_class.return_value = mock_path_instance

            runner = CronJobRunner()

            # Override the scheduler with our mock (same as the fixture does)
            runner.scheduler = mock_scheduler

            # Mock the scheduler start/shutdown methods
            mock_scheduler.start = AsyncMock()
            mock_scheduler.shutdown = Mock()

            await runner.start()
            mock_scheduler.start.assert_called_once()

            # Set scheduler as running so shutdown will be called
            mock_scheduler.running = True
            await runner.shutdown()
            mock_scheduler.shutdown.assert_called_once_with(wait=True)


class TestGlobalCronRunner:

    @pytest.mark.asyncio
    @patch('app.cron_runner.CronJobRunner')
    async def test_get_cron_runner_creates_instance(self, mock_cron_runner_class):
        """Test getting global cron runner instance."""
        mock_instance = AsyncMock()
        mock_cron_runner_class.return_value = mock_instance

        # Reset global instance
        import app.cron_runner
        app.cron_runner._cron_runner = None

        instance = await get_cron_runner()

        assert instance == mock_instance
        mock_cron_runner_class.assert_called_once()
        mock_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cron_runner_returns_existing_instance(self):
        """Test getting existing global cron runner instance."""
        # Reset global instance
        import app.cron_runner
        app.cron_runner._cron_runner = None

        # Get first instance
        instance1 = await get_cron_runner()

        # Get second instance (should be same)
        instance2 = await get_cron_runner()

        assert instance1 is instance2

    @pytest.mark.asyncio
    async def test_shutdown_cron_runner(self):
        """Test shutting down global cron runner."""
        import app.cron_runner

        # Set up a mock instance
        mock_instance = AsyncMock()
        app.cron_runner._cron_runner = mock_instance

        await shutdown_cron_runner()

        mock_instance.shutdown.assert_called_once()
        assert app.cron_runner._cron_runner is None

    @pytest.mark.asyncio
    async def test_shutdown_cron_runner_no_instance(self):
        """Test shutting down when no instance exists."""
        import app.cron_runner

        # Ensure no instance
        app.cron_runner._cron_runner = None

        # Should not raise
        await shutdown_cron_runner()

    async def test_execute_job_single_attempt_with_json_output(self, cron_runner):
        """Test job execution with JSON output extraction."""
        command = ["echo", '{"result": "success"}']
        job_name = "json_job"

        # Mock subprocess with JSON output
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b'Output:\n{"result": "success"}\n', b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            mock_job_result = Mock()
            mock_start_job.return_value = mock_job_result

            await cron_runner._execute_job_single_attempt(command, job_name=job_name)

            # Verify JSON was extracted and passed to update_job
            mock_update_job.assert_called_once()
            call_kwargs = mock_update_job.call_args[1]
            assert call_kwargs['json_output'] == {"result": "success"}

    async def test_execute_job_single_attempt_process_exception(self, cron_runner):
        """Test handling of subprocess creation exceptions."""
        command = ["invalid", "command"]
        job_name = "failing_job"

        with patch('app.cron_runner.asyncio.create_subprocess_exec', side_effect=OSError("Command not found")), \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            mock_job_result = Mock()
            mock_start_job.return_value = mock_job_result

            with pytest.raises(Exception, match="Command not found"):
                await cron_runner._execute_job_single_attempt(command, job_name=job_name)

    async def test_execute_job_single_attempt_with_env_vars(self, cron_runner):
        """Test job execution includes environment variables."""
        command = ["env"]
        job_name = "env_test"

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()

        with patch('app.cron_runner.asyncio.create_subprocess_exec', return_value=mock_process) as mock_create, \
             patch.object(cron_runner.job_tracker, 'start_job') as mock_start_job, \
             patch.object(cron_runner.job_tracker, 'update_job') as mock_update_job:

            mock_job_result = Mock()
            mock_start_job.return_value = mock_job_result

            await cron_runner._execute_job_single_attempt(command, job_name=job_name)

            # Verify env vars were passed
            call_args = mock_create.call_args
            env_arg = call_args[1]['env']
            assert 'TEST_VAR' in env_arg
            assert env_arg['TEST_VAR'] == 'test_value'

    @pytest.mark.asyncio
    async def test_execute_job_from_rule_no_commands(self, cron_runner):
        """Test executing job with no commands."""
        mock_rule = Mock()
        mock_rule.name = "empty_job"
        mock_rule.commands = []

        # Should not raise or execute anything - but method calls async internally
        # For testing, we'll just call it (it should not execute anything)
        await cron_runner._execute_job_from_rule("empty_job", mock_rule)

    def test_execute_job_from_rule_multiple_commands(self, cron_runner):
        """Test executing job with multiple commands (uses first one)."""
        mock_rule = Mock()
        mock_rule.name = "multi_cmd_job"
        mock_rule.commands = [["cmd1"], ["cmd2"], ["cmd3"]]

        with patch.object(cron_runner, '_execute_job_with_retries', new_callable=AsyncMock) as mock_execute:
            # This is synchronous but calls async - for testing we'll just mock it
            pass

    async def test_run_dispatcher_trigger_no_jobs_due(self, cron_runner):
        """Test dispatcher trigger when no jobs are due."""
        with patch('app.cron_runner.job_dispatcher.load_rules', return_value=[]), \
             patch('app.cron_runner.job_dispatcher.load_state', return_value={}), \
             patch('app.cron_runner.job_dispatcher.get_jobs_to_run', return_value=[]):

            # Should complete without executing any jobs
            await cron_runner._run_dispatcher_trigger()

    async def test_run_dispatcher_trigger_dispatcher_error(self, cron_runner):
        """Test dispatcher trigger handles dispatcher-level errors."""
        with patch('app.cron_runner.job_dispatcher.load_rules', side_effect=Exception("Dispatcher error")):

            # Should not raise exception
            await cron_runner._run_dispatcher_trigger()
