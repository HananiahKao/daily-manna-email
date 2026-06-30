"""Tests for dispatch_rules_validator schema validation."""

import pytest
from dispatch_rules_validator import validate_dispatch_rules, ValidationError


class TestValidateDispatchRules:
    """Test dispatch rules schema validation."""

    def test_valid_config_with_daily_send(self):
        """Test valid config with daily send rule."""
        config = [
            {
                "name": "daily-send",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "scripts/run_daily.sh"]],
            }
        ]
        validate_dispatch_rules(config)  # Should not raise

    def test_valid_config_with_weekday_integers(self):
        """Test valid config with integer weekday indices."""
        config = [
            {
                "name": "weekend-job",
                "time": "12:00",
                "days": [5, 6],  # Saturday, Sunday
                "commands": [["bash", "scripts/run_weekend.sh"]],
            }
        ]
        validate_dispatch_rules(config)

    def test_valid_config_with_mixed_weekdays(self):
        """Test valid config with mixed string and integer days."""
        config = [
            {
                "name": "mixed-days",
                "time": "18:00",
                "days": ["monday", 4, "fri"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        validate_dispatch_rules(config)

    def test_valid_config_with_env(self):
        """Test valid config with environment variables."""
        config = [
            {
                "name": "with-env",
                "time": "09:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
                "env": {"VAR1": "value1", "VAR2": "value2"},
            }
        ]
        validate_dispatch_rules(config)

    def test_valid_config_with_string_commands(self):
        """Test valid config with string commands (shell syntax)."""
        config = [
            {
                "name": "string-cmd",
                "time": "10:00",
                "days": ["daily"],
                "commands": ["python script.py arg1 arg2"],
            }
        ]
        validate_dispatch_rules(config)

    def test_valid_config_with_multiple_commands(self):
        """Test valid config with multiple commands."""
        config = [
            {
                "name": "multi-cmd",
                "time": "15:00",
                "days": ["daily"],
                "commands": [
                    ["bash", "script1.sh"],
                    "python script2.py",
                    ["python", "script3.py", "arg1"],
                ],
            }
        ]
        validate_dispatch_rules(config)

    def test_invalid_not_array(self):
        """Test that config must be an array."""
        config = {"name": "not-array"}
        with pytest.raises(ValidationError, match="must be an array"):
            validate_dispatch_rules(config)

    def test_invalid_empty_array(self):
        """Test that config array cannot be empty."""
        config = []
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_dispatch_rules(config)

    def test_invalid_rule_not_object(self):
        """Test that each rule must be an object."""
        config = ["not-an-object"]
        with pytest.raises(ValidationError, match="must be an object"):
            validate_dispatch_rules(config)

    def test_invalid_missing_name(self):
        """Test that name field is required."""
        config = [
            {
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="missing required field 'name'"):
            validate_dispatch_rules(config)

    def test_invalid_missing_time(self):
        """Test that time field is required."""
        config = [
            {
                "name": "no-time",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="missing required field 'time'"):
            validate_dispatch_rules(config)

    def test_invalid_missing_commands(self):
        """Test that commands field is required."""
        config = [
            {
                "name": "no-commands",
                "time": "06:00",
                "days": ["daily"],
            }
        ]
        with pytest.raises(ValidationError, match="missing required field 'commands'"):
            validate_dispatch_rules(config)

    def test_invalid_missing_days_and_weekdays(self):
        """Test that days or weekdays field is required."""
        config = [
            {
                "name": "no-days",
                "time": "06:00",
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="missing required field 'days' or 'weekdays'"):
            validate_dispatch_rules(config)

    def test_invalid_name_not_string(self):
        """Test that name must be a string."""
        config = [
            {
                "name": 123,
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="'name' must be string"):
            validate_dispatch_rules(config)

    def test_invalid_name_empty_string(self):
        """Test that name cannot be empty."""
        config = [
            {
                "name": "",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="'name' cannot be empty"):
            validate_dispatch_rules(config)

    def test_invalid_time_format(self):
        """Test that time must be in HH:MM format."""
        config = [
            {
                "name": "bad-time",
                "time": "6:00",  # Missing leading zero
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        # Actually 6:00 is valid, let me use an actual invalid format
        config[0]["time"] = "25:00"  # Invalid hour
        with pytest.raises(ValidationError, match="must be valid HH:MM format"):
            validate_dispatch_rules(config)

    def test_invalid_time_not_string(self):
        """Test that time must be a string."""
        config = [
            {
                "name": "time-int",
                "time": 600,
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="'time' must be string"):
            validate_dispatch_rules(config)

    def test_invalid_days_not_array(self):
        """Test that days must be an array."""
        config = [
            {
                "name": "days-string",
                "time": "06:00",
                "days": "daily",
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="'days' must be array"):
            validate_dispatch_rules(config)

    def test_invalid_days_empty_array(self):
        """Test that days array cannot be empty."""
        config = [
            {
                "name": "days-empty",
                "time": "06:00",
                "days": [],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="'days' array cannot be empty"):
            validate_dispatch_rules(config)

    def test_invalid_weekday_index_negative(self):
        """Test that weekday index must be 0-6."""
        config = [
            {
                "name": "bad-weekday",
                "time": "06:00",
                "days": [-1],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="weekday index must be 0-6"):
            validate_dispatch_rules(config)

    def test_invalid_weekday_index_too_high(self):
        """Test that weekday index must be 0-6."""
        config = [
            {
                "name": "bad-weekday",
                "time": "06:00",
                "days": [7],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="weekday index must be 0-6"):
            validate_dispatch_rules(config)

    def test_invalid_weekday_type(self):
        """Test that weekday must be int or string."""
        config = [
            {
                "name": "bad-weekday-type",
                "time": "06:00",
                "days": [3.14],
                "commands": [["bash", "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="must be integer.*or string"):
            validate_dispatch_rules(config)

    def test_invalid_commands_not_array(self):
        """Test that commands must be an array."""
        config = [
            {
                "name": "commands-string",
                "time": "06:00",
                "days": ["daily"],
                "commands": "bash script.sh",
            }
        ]
        with pytest.raises(ValidationError, match="'commands' must be array"):
            validate_dispatch_rules(config)

    def test_invalid_commands_empty_array(self):
        """Test that commands array cannot be empty."""
        config = [
            {
                "name": "commands-empty",
                "time": "06:00",
                "days": ["daily"],
                "commands": [],
            }
        ]
        with pytest.raises(ValidationError, match="'commands' array cannot be empty"):
            validate_dispatch_rules(config)

    def test_invalid_command_item_type(self):
        """Test that command items must be string or array."""
        config = [
            {
                "name": "bad-cmd-type",
                "time": "06:00",
                "days": ["daily"],
                "commands": [123],
            }
        ]
        with pytest.raises(ValidationError, match="must be string or array"):
            validate_dispatch_rules(config)

    def test_invalid_command_array_empty(self):
        """Test that command array cannot be empty."""
        config = [
            {
                "name": "cmd-array-empty",
                "time": "06:00",
                "days": ["daily"],
                "commands": [[]],
            }
        ]
        with pytest.raises(ValidationError, match="array cannot be empty"):
            validate_dispatch_rules(config)

    def test_invalid_command_array_item_not_string(self):
        """Test that command array items must be strings."""
        config = [
            {
                "name": "cmd-array-bad-item",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", 123, "script.sh"]],
            }
        ]
        with pytest.raises(ValidationError, match="must be string"):
            validate_dispatch_rules(config)

    def test_invalid_env_not_object(self):
        """Test that env must be an object."""
        config = [
            {
                "name": "env-bad",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
                "env": ["VAR1=value1"],
            }
        ]
        with pytest.raises(ValidationError, match="'env' must be object"):
            validate_dispatch_rules(config)

    def test_invalid_env_value_not_string(self):
        """Test that env values must be strings."""
        config = [
            {
                "name": "env-value-bad",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
                "env": {"VAR1": 123},
            }
        ]
        with pytest.raises(ValidationError, match="must be string"):
            validate_dispatch_rules(config)

    def test_multiple_rules_validates_all(self):
        """Test that validation checks all rules, not just first."""
        config = [
            {
                "name": "valid-1",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script1.sh"]],
            },
            {
                "name": "invalid-2",
                "time": "25:00",  # Invalid
                "days": ["daily"],
                "commands": [["bash", "script2.sh"]],
            },
        ]
        with pytest.raises(ValidationError, match="must be valid HH:MM format"):
            validate_dispatch_rules(config)

    def test_error_message_includes_rule_index(self):
        """Test that error messages include the rule index for debugging."""
        config = [
            {
                "name": "rule-0",
                "time": "06:00",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            },
            {
                "name": "rule-1",
                "time": "bad-time",
                "days": ["daily"],
                "commands": [["bash", "script.sh"]],
            },
        ]
        with pytest.raises(ValidationError) as exc_info:
            validate_dispatch_rules(config)
        assert "Rule 1" in str(exc_info.value)
