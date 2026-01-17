import datetime as dt
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import schedule_manager as sm

from app.job_tracker import JobTracker, JobExecutionResult, get_job_tracker


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def job_tracker(temp_state_dir):
    """Create a job tracker with temporary storage."""
    return JobTracker(storage_path=temp_state_dir / "job_history.json")


class TestJobExecutionResult:

    def test_init(self):
        """Test JobExecutionResult initialization."""
        start_time = dt.datetime.now(tz=sm.TAIWAN_TZ)
        job = JobExecutionResult(
            job_name="test_job",
            start_time=start_time,
            max_retries=3
        )

        assert job.job_name == "test_job"
        assert job.start_time == start_time
        assert job.status == "running"
        assert job.max_retries == 3
        assert job.logs == []
        assert job.metadata == {}

    def test_duration_seconds_no_end_time(self):
        """Test duration calculation when job hasn't finished."""
        start_time = dt.datetime.now(tz=sm.TAIWAN_TZ)
        job = JobExecutionResult(job_name="test", start_time=start_time)

        assert job.duration_seconds is None

    def test_duration_seconds_with_end_time(self):
        """Test duration calculation when job has finished."""
        start_time = dt.datetime(2025, 1, 1, 10, 0, 0, tzinfo=sm.TAIWAN_TZ)
        end_time = dt.datetime(2025, 1, 1, 10, 5, 30, tzinfo=sm.TAIWAN_TZ)

        job = JobExecutionResult(
            job_name="test",
            start_time=start_time,
            end_time=end_time
        )

        assert job.duration_seconds == 330.0  # 5 minutes 30 seconds

    def test_is_success(self):
        """Test success status check."""
        job = JobExecutionResult(job_name="test", start_time=dt.datetime.now(tz=sm.TAIWAN_TZ))

        job.status = "success"
        assert job.is_success is True

        job.status = "failed"
        assert job.is_success is False

    def test_is_failed(self):
        """Test failed status check."""
        job = JobExecutionResult(job_name="test", start_time=dt.datetime.now(tz=sm.TAIWAN_TZ))

        job.status = "failed"
        assert job.is_failed is True

        job.status = "success"
        assert job.is_failed is False

    def test_is_running(self):
        """Test running status check."""
        job = JobExecutionResult(job_name="test", start_time=dt.datetime.now(tz=sm.TAIWAN_TZ))

        job.status = "running"
        assert job.is_running is True

        job.status = "success"
        assert job.is_running is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        start_time = dt.datetime(2025, 1, 1, 10, 0, 0, tzinfo=sm.TAIWAN_TZ)
        end_time = dt.datetime(2025, 1, 1, 10, 1, 0, tzinfo=sm.TAIWAN_TZ)

        job = JobExecutionResult(
            job_name="test_job",
            start_time=start_time,
            end_time=end_time,
            status="success",
            exit_code=0,
            json_output={"result": "ok"},
            logs=["Starting job", "Job completed"],
            retry_count=1,
            max_retries=3,
            error_message=None,
            metadata={"command": ["echo", "test"]}
        )

        data = job.to_dict()

        assert data["job_name"] == "test_job"
        assert data["status"] == "success"
        assert data["exit_code"] == 0
        assert data["json_output"] == {"result": "ok"}
        assert data["logs"] == ["Starting job", "Job completed"]
        assert data["retry_count"] == 1
        assert data["max_retries"] == 3
        assert data["error_message"] is None
        assert data["metadata"] == {"command": ["echo", "test"]}
        assert data["duration_seconds"] == 60.0

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "job_name": "test_job",
            "start_time": "2025-01-01T10:00:00+08:00",
            "end_time": "2025-01-01T10:01:00+08:00",
            "status": "success",
            "exit_code": 0,
            "json_output": {"result": "ok"},
            "logs": ["Starting job", "Job completed"],
            "retry_count": 1,
            "max_retries": 3,
            "error_message": None,
            "metadata": {"command": ["echo", "test"]}
        }

        job = JobExecutionResult.from_dict(data)

        assert job.job_name == "test_job"
        assert job.status == "success"
        assert job.exit_code == 0
        assert job.json_output == {"result": "ok"}
        assert job.logs == ["Starting job", "Job completed"]
        assert job.retry_count == 1
        assert job.max_retries == 3
        assert job.error_message is None
        assert job.metadata == {"command": ["echo", "test"]}


class TestJobTracker:

    def test_init_creates_storage_file(self, temp_state_dir):
        """Test JobTracker initialization creates storage file."""
        storage_path = temp_state_dir / "job_history.json"
        tracker = JobTracker(storage_path=storage_path)

        # File is created when first job is saved
        job = tracker.start_job("test_job")
        tracker.update_job(job, status="success")

        assert storage_path.exists()
        assert tracker.storage_path == storage_path
        assert len(tracker._current_jobs) == 1

    def test_init_loads_existing_history(self, temp_state_dir):
        """Test loading existing job history on initialization."""
        storage_path = temp_state_dir / "job_history.json"

        # Create existing history file with recent job
        recent_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(hours=1)
        existing_data = {
            "last_updated": dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat(),
            "executions": [{
                "job_name": "recent_job",
                "start_time": recent_time.isoformat(),
                "end_time": (recent_time + dt.timedelta(minutes=1)).isoformat(),
                "status": "success",
                "exit_code": 0,
                "json_output": None,
                "logs": ["Completed"],
                "retry_count": 0,
                "max_retries": 3,
                "error_message": None,
                "metadata": {}
            }]
        }

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f)

        tracker = JobTracker(storage_path=storage_path)

        # Should have loaded the recent job
        assert len(tracker._current_jobs) == 1
        loaded_job = list(tracker._current_jobs.values())[0]
        assert loaded_job.job_name == "recent_job"
        assert loaded_job.status == "success"

    def test_init_handles_corrupted_history_file(self, temp_state_dir):
        """Test handling of corrupted history file."""
        storage_path = temp_state_dir / "job_history.json"

        # Create corrupted JSON file
        with open(storage_path, 'w', encoding='utf-8') as f:
            f.write("invalid json content")

        # Should not raise exception
        tracker = JobTracker(storage_path=storage_path)

        # Should start with empty history
        assert tracker._current_jobs == {}

    def test_start_job(self, job_tracker):
        """Test starting a new job."""
        job_name = "test_job"
        max_retries = 2

        job = job_tracker.start_job(job_name, max_retries)

        assert job.job_name == job_name
        assert job.max_retries == max_retries
        assert job.status == "running"
        assert job.start_time is not None

        # Should be in current jobs
        key = f"{job_name}_{job.start_time.isoformat()}"
        assert key in job_tracker._current_jobs

    def test_update_job_basic(self, job_tracker):
        """Test basic job update."""
        job = job_tracker.start_job("test_job")

        job_tracker.update_job(
            job,
            status="success",
            exit_code=0,
            logs=["Job completed successfully"]
        )

        assert job.status == "success"
        assert job.exit_code == 0
        assert job.logs == ["Job completed successfully"]
        assert job.end_time is not None

    def test_update_job_with_json_output(self, job_tracker):
        """Test job update with JSON output."""
        job = job_tracker.start_job("test_job")

        json_output = {"result": "success", "count": 42}

        job_tracker.update_job(job, json_output=json_output)

        assert job.json_output == json_output

    def test_update_job_with_error(self, job_tracker):
        """Test job update with error message."""
        job = job_tracker.start_job("test_job")

        error_msg = "Command failed"

        job_tracker.update_job(
            job,
            status="failed",
            error_message=error_msg,
            logs=["Error occurred"]
        )

        assert job.status == "failed"
        assert job.error_message == error_msg
        assert job.logs == ["Error occurred"]

    def test_update_job_with_metadata(self, job_tracker):
        """Test job update with metadata."""
        job = job_tracker.start_job("test_job")

        metadata = {"command": ["echo", "test"], "timeout": 30}

        job_tracker.update_job(job, metadata=metadata)

        assert job.metadata == metadata

    def test_retry_job_within_limit(self, job_tracker):
        """Test retrying a job within retry limit."""
        job = job_tracker.start_job("test_job", max_retries=2)
        original_start = job.start_time

        # First retry should succeed
        can_retry = job_tracker.retry_job(job)

        assert can_retry is True
        assert job.retry_count == 1
        assert job.status == "running"
        assert job.start_time > original_start  # New start time
        assert job.end_time is None
        assert job.error_message is None

    def test_retry_job_exceeds_limit(self, job_tracker):
        """Test retrying a job that exceeds retry limit."""
        job = job_tracker.start_job("test_job", max_retries=1)
        job.retry_count = 1  # Already at limit

        can_retry = job_tracker.retry_job(job)

        assert can_retry is False
        assert job.retry_count == 1  # Should not increment

    def test_get_recent_executions_no_filter(self, job_tracker):
        """Test getting recent executions without filtering."""
        # Create multiple jobs
        job1 = job_tracker.start_job("job1")
        job_tracker.update_job(job1, status="success")

        job2 = job_tracker.start_job("job2")
        job_tracker.update_job(job2, status="failed")

        recent = job_tracker.get_recent_executions()

        assert len(recent) == 2
        # Should be sorted by start time, most recent first
        assert recent[0].job_name == "job2"
        assert recent[1].job_name == "job1"

    def test_get_recent_executions_with_filter(self, job_tracker):
        """Test getting recent executions with job name filter."""
        job1 = job_tracker.start_job("job1")
        job_tracker.update_job(job1, status="success")

        job2 = job_tracker.start_job("job2")
        job_tracker.update_job(job2, status="failed")

        recent = job_tracker.get_recent_executions(job_name="job1")

        assert len(recent) == 1
        assert recent[0].job_name == "job1"

    def test_get_recent_executions_with_limit(self, job_tracker):
        """Test getting recent executions with limit."""
        # Create 3 jobs
        for i in range(3):
            job = job_tracker.start_job(f"job{i}")
            job_tracker.update_job(job, status="success")

        recent = job_tracker.get_recent_executions(limit=2)

        assert len(recent) == 2

    def test_get_job_stats_no_jobs(self, job_tracker):
        """Test getting stats when no jobs exist."""
        stats = job_tracker.get_job_stats()

        expected = {
            "total_runs": 0,
            "success_rate": 0.0,
            "average_duration": 0.0,
            "last_run": None,
            "status_counts": {}
        }

        assert stats == expected

    def test_get_job_stats_with_jobs(self, job_tracker):
        """Test getting stats with existing jobs."""
        # Create successful job with controlled duration
        job1 = job_tracker.start_job("test_job")
        job1.start_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(minutes=2)  # 2 minutes ago
        job_tracker.update_job(job1, status="success")
        job1.end_time = job1.start_time + dt.timedelta(minutes=1)  # 1 minute duration

        # Create failed job with controlled duration
        job2 = job_tracker.start_job("test_job")
        job2.start_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(minutes=1)  # 1 minute ago
        job_tracker.update_job(job2, status="failed")
        job2.end_time = job2.start_time + dt.timedelta(seconds=30)  # 30 second duration

        stats = job_tracker.get_job_stats()

        assert stats["total_runs"] == 2
        assert stats["success_rate"] == 0.5
        assert abs(stats["average_duration"] - 45.0) < 0.1  # (60 + 30) / 2
        assert stats["status_counts"] == {"success": 1, "failed": 1}

    def test_get_job_stats_filtered(self, job_tracker):
        """Test getting stats filtered by job name."""
        # Create jobs for different job names
        job1 = job_tracker.start_job("job1")
        job_tracker.update_job(job1, status="success")

        job2 = job_tracker.start_job("job2")
        job_tracker.update_job(job2, status="success")

        stats = job_tracker.get_job_stats(job_name="job1")

        assert stats["total_runs"] == 1
        assert stats["success_rate"] == 1.0

    def test_history_cleanup_on_load(self, temp_state_dir):
        """Test that old jobs are cleaned up when loading history."""
        storage_path = temp_state_dir / "job_history.json"

        # Create history with old and recent jobs
        old_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(days=40)  # Older than 30 days
        recent_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(days=10)

        existing_data = {
            "last_updated": dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat(),
            "executions": [
                {
                    "job_name": "old_job",
                    "start_time": old_time.isoformat(),
                    "end_time": (old_time + dt.timedelta(minutes=1)).isoformat(),
                    "status": "success",
                    "exit_code": 0,
                    "json_output": None,
                    "logs": [],
                    "retry_count": 0,
                    "max_retries": 3,
                    "error_message": None,
                    "metadata": {}
                },
                {
                    "job_name": "recent_job",
                    "start_time": recent_time.isoformat(),
                    "end_time": (recent_time + dt.timedelta(minutes=1)).isoformat(),
                    "status": "success",
                    "exit_code": 0,
                    "json_output": None,
                    "logs": [],
                    "retry_count": 0,
                    "max_retries": 3,
                    "error_message": None,
                    "metadata": {}
                }
            ]
        }

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f)

        tracker = JobTracker(storage_path=storage_path)

        # Should only have the recent job
        assert len(tracker._current_jobs) == 1
        remaining_job = list(tracker._current_jobs.values())[0]
        assert remaining_job.job_name == "recent_job"

    def test_save_history_atomic_write(self, job_tracker):
        """Test that history is saved atomically."""
        job = job_tracker.start_job("test_job")
        job_tracker.update_job(job, status="success")

        # File should exist and be valid JSON
        assert job_tracker.storage_path.exists()

        with open(job_tracker.storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "executions" in data
        assert len(data["executions"]) == 1
        assert data["executions"][0]["job_name"] == "test_job"


class TestGlobalJobTracker:

    @patch('app.job_tracker.JobTracker')
    def test_get_job_tracker_creates_instance(self, mock_tracker_class):
        """Test getting global job tracker instance."""
        mock_instance = Mock()
        mock_tracker_class.return_value = mock_instance

        # Reset global instance
        import app.job_tracker
        app.job_tracker._job_tracker = None

        instance = get_job_tracker()

        assert instance == mock_instance
        mock_tracker_class.assert_called_once()

    def test_get_job_tracker_returns_existing_instance(self):
        """Test getting existing global job tracker instance."""
        # Reset global instance
        import app.job_tracker
        app.job_tracker._job_tracker = None

        # Get first instance
        instance1 = get_job_tracker()

        # Get second instance (should be same)
        instance2 = get_job_tracker()

        assert instance1 is instance2

    def test_job_result_properties(self):
        """Test JobExecutionResult property methods."""
        start_time = dt.datetime(2025, 1, 1, 10, 0, 0, tzinfo=sm.TAIWAN_TZ)
        end_time = dt.datetime(2025, 1, 1, 10, 1, 0, tzinfo=sm.TAIWAN_TZ)

        job = JobExecutionResult(
            job_name="test",
            start_time=start_time,
            end_time=end_time
        )

        # Test properties
        assert job.duration_seconds == 60.0
        assert job.is_success is False  # status is still "running"
        assert job.is_failed is False
        assert job.is_running is True

        # Change status and test again
        job.status = "success"
        assert job.is_success is True
        assert job.is_failed is False
        assert job.is_running is False

        job.status = "failed"
        assert job.is_success is False
        assert job.is_failed is True
        assert job.is_running is False

    def test_job_tracker_save_load_corrupted_file(self, temp_state_dir):
        """Test handling of corrupted storage file during load."""
        storage_path = temp_state_dir / "job_history.json"

        # Create corrupted file
        with open(storage_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json")

        tracker = JobTracker(storage_path=storage_path)

        # Should initialize without error
        assert tracker._current_jobs == {}

    def test_job_tracker_atomic_save_with_existing_file(self, job_tracker):
        """Test atomic save when file already exists."""
        # Create initial job
        job1 = job_tracker.start_job("job1")
        job_tracker.update_job(job1, status="success")

        # Modify the file to simulate concurrent access
        with open(job_tracker.storage_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # Add another job
        job2 = job_tracker.start_job("job2")
        job_tracker.update_job(job2, status="success")

        # File should be updated atomically
        with open(job_tracker.storage_path, 'r', encoding='utf-8') as f:
            new_content = f.read()

        assert new_content != original_content
        assert "job1" in new_content
        assert "job2" in new_content

    def test_job_tracker_history_cleanup_edge_cases(self, temp_state_dir):
        """Test history cleanup with edge cases."""
        storage_path = temp_state_dir / "job_history.json"

        # Create history with jobs around the 30-day cutoff
        cutoff_time = dt.datetime.now(tz=sm.TAIWAN_TZ) - dt.timedelta(days=30)

        existing_data = {
            "last_updated": dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat(),
            "executions": [
                {
                    "job_name": "within_30_days",
                    "start_time": (cutoff_time + dt.timedelta(seconds=1)).isoformat(),  # Just within 30 days
                    "end_time": (cutoff_time + dt.timedelta(seconds=1) + dt.timedelta(minutes=1)).isoformat(),
                    "status": "success",
                    "exit_code": 0,
                    "json_output": None,
                    "logs": [],
                    "retry_count": 0,
                    "max_retries": 3,
                    "error_message": None,
                    "metadata": {}
                },
                {
                    "job_name": "older_than_30_days",
                    "start_time": (cutoff_time - dt.timedelta(seconds=1)).isoformat(),  # Just over 30 days
                    "end_time": (cutoff_time - dt.timedelta(seconds=1) + dt.timedelta(minutes=1)).isoformat(),
                    "status": "success",
                    "exit_code": 0,
                    "json_output": None,
                    "logs": [],
                    "retry_count": 0,
                    "max_retries": 3,
                    "error_message": None,
                    "metadata": {}
                }
            ]
        }

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f)

        tracker = JobTracker(storage_path=storage_path)

        # Should keep the job within 30 days, remove older ones
        assert len(tracker._current_jobs) == 1
        remaining_job = list(tracker._current_jobs.values())[0]
        assert remaining_job.job_name == "within_30_days"
