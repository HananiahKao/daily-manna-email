#!/usr/bin/env python3
"""
Test job-specific environment variable configuration.

This test verifies that:
1. Job-specific environment variables are properly parsed from JSON config
2. Job-specific variables override global variables
3. Jobs without env variables still work with global variables
4. Environment variables are properly passed to subprocesses
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Any

import pytest

from app.cron_runner import CronJobRunner
import job_dispatcher


class TestJobSpecificEnvironmentVariables:
    """Test job-specific environment variable functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.project_root = self.test_dir
        self.env_file = self.test_dir / ".env"
        self.config_file = self.test_dir / "config" / "dispatch_rules.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        # Create a mock CronJobRunner for testing
        self.runner = CronJobRunner()
        self.runner.project_root = self.test_dir

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_global_env_vars_only(self):
        """Test that jobs work with only global environment variables."""
        # Create .env file with global variables
        self.env_file.write_text("GLOBAL_VAR=global_value\nANOTHER_VAR=another_value\n")
        
        # Create config without job-specific env vars
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]]
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "test-job"
        assert rule.env is None
        
        # Test environment variable loading
        env_vars = self.runner._get_env_vars()
        assert env_vars["GLOBAL_VAR"] == "global_value"
        assert env_vars["ANOTHER_VAR"] == "another_value"
        
        # Test job-specific env vars (should be same as global)
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars["GLOBAL_VAR"] == "global_value"
        assert job_env_vars["ANOTHER_VAR"] == "another_value"

    def test_job_specific_env_vars_override_global(self):
        """Test that job-specific environment variables override global ones."""
        # Create .env file with global variables
        self.env_file.write_text("GLOBAL_VAR=global_value\nSHARED_VAR=global_shared\n")
        
        # Create config with job-specific env vars
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {
                    "JOB_SPECIFIC_VAR": "job_value",
                    "SHARED_VAR": "job_shared",  # This should override global
                    "ANOTHER_JOB_VAR": "another_value"
                }
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "test-job"
        assert rule.env is not None
        assert rule.env["JOB_SPECIFIC_VAR"] == "job_value"
        assert rule.env["SHARED_VAR"] == "job_shared"
        
        # Test environment variable loading
        global_env_vars = self.runner._get_env_vars()
        assert global_env_vars["GLOBAL_VAR"] == "global_value"
        assert global_env_vars["SHARED_VAR"] == "global_shared"
        
        # Test job-specific env vars (should combine global + job-specific with override)
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars["GLOBAL_VAR"] == "global_value"  # From global
        assert job_env_vars["SHARED_VAR"] == "job_shared"    # Job-specific overrides global
        assert job_env_vars["JOB_SPECIFIC_VAR"] == "job_value"  # Job-specific only
        assert job_env_vars["ANOTHER_JOB_VAR"] == "another_value"  # Job-specific only

    def test_job_without_env_vars_uses_global(self):
        """Test that jobs without env vars still get global variables."""
        # Create .env file with global variables
        self.env_file.write_text("GLOBAL_VAR=global_value\n")
        
        # Create config without env field
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]]
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "test-job"
        assert rule.env is None
        
        # Test job-specific env vars (should be same as global)
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars["GLOBAL_VAR"] == "global_value"

    def test_empty_env_vars(self):
        """Test that empty env vars work correctly."""
        # Create config with empty env
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {}
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "test-job"
        assert rule.env == {}
        
        # Test job-specific env vars (should be empty dict)
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars == {}

    def test_multiple_jobs_with_different_envs(self):
        """Test multiple jobs with different environment variable configurations."""
        # Create .env file with global variables
        self.env_file.write_text("GLOBAL_VAR=global_value\nSHARED_VAR=global_shared\n")
        
        # Create config with multiple jobs having different env configs
        config = [
            {
                "name": "job-with-env",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {
                    "JOB_SPECIFIC_VAR": "job1_value",
                    "SHARED_VAR": "job1_shared"
                }
            },
            {
                "name": "job-without-env",
                "time": "07:00",
                "days": ["daily"],
                "commands": [["echo", "test"]]
            },
            {
                "name": "job-with-different-env",
                "time": "08:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {
                    "DIFFERENT_VAR": "job3_value",
                    "ANOTHER_VAR": "job3_another"
                }
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 3
        
        # Test job 1 (with env)
        job1_rule = next((r for r in rules if r.name == "job-with-env"), None)
        assert job1_rule is not None
        job1_env = self.runner._get_job_env_vars(job1_rule)
        assert job1_env["GLOBAL_VAR"] == "global_value"  # From global
        assert job1_env["SHARED_VAR"] == "job1_shared"   # Job-specific overrides
        assert job1_env["JOB_SPECIFIC_VAR"] == "job1_value"  # Job-specific only
        
        # Test job 2 (without env)
        job2_rule = next((r for r in rules if r.name == "job-without-env"), None)
        assert job2_rule is not None
        job2_env = self.runner._get_job_env_vars(job2_rule)
        assert job2_env["GLOBAL_VAR"] == "global_value"  # From global
        assert job2_env["SHARED_VAR"] == "global_shared"  # From global
        
        # Test job 3 (with different env)
        job3_rule = next((r for r in rules if r.name == "job-with-different-env"), None)
        assert job3_rule is not None
        job3_env = self.runner._get_job_env_vars(job3_rule)
        assert job3_env["GLOBAL_VAR"] == "global_value"  # From global
        assert job3_env["SHARED_VAR"] == "global_shared"  # From global (not overridden)
        assert job3_env["DIFFERENT_VAR"] == "job3_value"  # Job-specific only
        assert job3_env["ANOTHER_VAR"] == "job3_another"  # Job-specific only

    def test_env_vars_with_special_characters(self):
        """Test environment variables with special characters."""
        # Create .env file with special characters
        self.env_file.write_text("SPECIAL_VAR=special_value_with_!@#$%^&*()\n")
        
        # Create config with job-specific env vars containing special characters
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {
                    "JOB_SPECIAL_VAR": "job_value_with_!@#$%^&*()",
                    "PATH_VAR": "/usr/local/bin:/usr/bin"
                }
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.env is not None
        assert rule.env["JOB_SPECIAL_VAR"] == "job_value_with_!@#$%^&*()"
        assert rule.env["PATH_VAR"] == "/usr/local/bin:/usr/bin"
        
        # Test job-specific env vars
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars["SPECIAL_VAR"] == "special_value_with_!@#$%^&*()"
        assert job_env_vars["JOB_SPECIAL_VAR"] == "job_value_with_!@#$%^&*()"
        assert job_env_vars["PATH_VAR"] == "/usr/local/bin:/usr/bin"

    def test_backward_compatibility(self):
        """Test that existing configurations without env field still work."""
        # Create .env file
        self.env_file.write_text("EXISTING_VAR=existing_value\n")
        
        # Create config in old format (without env field)
        config = [
            {
                "name": "existing-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]]
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "existing-job"
        assert rule.env is None  # Should be None for backward compatibility
        
        # Test that job still gets global environment variables
        job_env_vars = self.runner._get_job_env_vars(rule)
        assert job_env_vars["EXISTING_VAR"] == "existing_value"

    def test_env_vars_in_subprocess_execution(self):
        """Test that environment variables are properly passed to subprocesses."""
        # Create .env file
        self.env_file.write_text("GLOBAL_TEST=global_test_value\n")
        
        # Create config with job-specific env vars
        config = [
            {
                "name": "test-job",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["echo", "test"]],
                "env": {
                    "JOB_TEST": "job_test_value",
                    "GLOBAL_TEST": "job_test_override"  # Should override global
                }
            }
        ]
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        
        # Load rules and verify
        rules = job_dispatcher.load_rules(self.config_file)
        assert len(rules) == 1
        rule = rules[0]
        assert rule is not None
        
        # Test that the environment variables would be passed correctly
        # (We can't actually run the subprocess in this test, but we can verify
        # that the environment variables are constructed correctly)
        job_env_vars = self.runner._get_job_env_vars(rule)
        
        # Verify the environment variables that would be passed to subprocess
        expected_env = {
            "GLOBAL_TEST": "job_test_override",  # Job-specific overrides global
            "JOB_TEST": "job_test_value"         # Job-specific only
        }
        
        # Check that our job-specific env vars contain the expected values
        for key, expected_value in expected_env.items():
            actual_value = job_env_vars.get(key)
            assert actual_value == expected_value, f"Expected {key}={expected_value}, got {actual_value}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])