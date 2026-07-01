#!/usr/bin/env python3
"""
Validation for dispatch_rules.json schema.

Ensures dispatch rules have correct structure and valid values before
being loaded by job_dispatcher.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class ValidationError(ValueError):
    """Raised when dispatch rules fail validation."""
    pass


def validate_dispatch_rules(rules: Any) -> None:
    """Validate dispatch rules against schema.

    Args:
        rules: Parsed JSON from dispatch_rules.json

    Raises:
        ValidationError: If any rule violates the schema
    """
    if not isinstance(rules, list):
        raise ValidationError("Dispatch rules must be an array (list)")

    if not rules:
        raise ValidationError("Dispatch rules array cannot be empty")

    for idx, rule in enumerate(rules):
        _validate_rule(rule, idx)


def _get_rule_label(rule: Any, index: int) -> str:
    """Get rule label for error messages (includes name if available)."""
    if isinstance(rule, dict) and "name" in rule:
        return f"Rule {index} ('{rule['name']}')"
    return f"Rule {index}"


def _validate_rule(rule: Any, index: int) -> None:
    """Validate a single dispatch rule."""
    if not isinstance(rule, dict):
        raise ValidationError(f"Rule {index}: must be an object (dict), got {type(rule).__name__}")

    # Check required fields
    if "name" not in rule:
        raise ValidationError(f"Rule {index}: missing required field 'name'")

    if "time" not in rule:
        raise ValidationError(f"Rule {index}: missing required field 'time'")

    if "commands" not in rule:
        raise ValidationError(f"Rule {index}: missing required field 'commands'")

    # Validate name
    name = rule["name"]
    if not isinstance(name, str):
        raise ValidationError(f"Rule {index}: 'name' must be string, got {type(name).__name__}")
    if not name.strip():
        raise ValidationError(f"Rule {index}: 'name' cannot be empty")

    rule_label = _get_rule_label(rule, index)

    # Check if rule is disabled
    if rule.get("active") is False:
        return

    # Validate time
    _validate_time_field(rule.get("time"), index, rule_label)

    # Validate days/weekdays (allow empty as fallback for disabled rules)
    has_days = "days" in rule
    has_weekdays = "weekdays" in rule

    if not has_days and not has_weekdays:
        raise ValidationError(f"{rule_label}: missing required field 'days' or 'weekdays'")

    if has_days:
        days = rule["days"]
        if isinstance(days, list) and not days:
            # Empty days array = disabled (fallback compatibility)
            pass
        else:
            _validate_weekdays_field(days, index, rule_label, field_name="days")

    if has_weekdays:
        _validate_weekdays_field(rule["weekdays"], index, rule_label, field_name="weekdays")

    # Validate commands
    _validate_commands_field(rule["commands"], index, rule_label)

    # Validate active field (optional)
    if "active" in rule:
        active = rule["active"]
        if not isinstance(active, bool):
            raise ValidationError(
                f"{rule_label}: 'active' must be boolean, got {type(active).__name__}"
            )

    # Validate env (optional)
    if "env" in rule:
        env = rule["env"]
        if not isinstance(env, dict):
            raise ValidationError(
                f"{rule_label}: 'env' must be object (dict), got {type(env).__name__}"
            )
        for env_key, env_val in env.items():
            if not isinstance(env_key, str):
                raise ValidationError(f"{rule_label}: env keys must be strings")
            if not isinstance(env_val, str):
                raise ValidationError(
                    f"{rule_label}: env value for '{env_key}' must be string, got {type(env_val).__name__}"
                )


def _validate_time_field(time_val: Any, index: int, rule_label: str) -> None:
    """Validate time field is in HH:MM format."""
    if not isinstance(time_val, str):
        raise ValidationError(
            f"{rule_label}: 'time' must be string (HH:MM format), got {type(time_val).__name__}"
        )

    # Check HH:MM format
    time_pattern = r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    if not re.match(time_pattern, time_val.strip()):
        raise ValidationError(
            f"{rule_label}: 'time' must be valid HH:MM format (00:00-23:59), got '{time_val}'"
        )


def _validate_weekdays_field(
    weekdays: Any,
    index: int,
    rule_label: str,
    field_name: str = "days"
) -> None:
    """Validate weekdays/days field."""
    if not isinstance(weekdays, list):
        raise ValidationError(
            f"{rule_label}: '{field_name}' must be array, got {type(weekdays).__name__}"
        )

    if not weekdays:
        raise ValidationError(f"{rule_label}: '{field_name}' array cannot be empty")

    for item_idx, item in enumerate(weekdays):
        if isinstance(item, int):
            if not 0 <= item <= 6:
                raise ValidationError(
                    f"{rule_label}: '{field_name}[{item_idx}]' weekday index must be 0-6, got {item}"
                )
        elif isinstance(item, str):
            if not item.strip():
                raise ValidationError(f"{rule_label}: '{field_name}[{item_idx}]' cannot be empty string")
            # Valid day names checked by job_dispatcher's WEEKDAY_MAP
        else:
            raise ValidationError(
                f"{rule_label}: '{field_name}[{item_idx}]' must be integer (0-6) or string, "
                f"got {type(item).__name__}"
            )


def _validate_commands_field(commands: Any, index: int, rule_label: str) -> None:
    """Validate commands field."""
    if not isinstance(commands, list):
        raise ValidationError(
            f"{rule_label}: 'commands' must be array, got {type(commands).__name__}"
        )

    if not commands:
        raise ValidationError(f"{rule_label}: 'commands' array cannot be empty")

    for cmd_idx, cmd in enumerate(commands):
        if isinstance(cmd, str):
            # String command is allowed
            if not cmd.strip():
                raise ValidationError(f"{rule_label}: 'commands[{cmd_idx}]' cannot be empty string")
        elif isinstance(cmd, list):
            # Array of strings
            if not cmd:
                raise ValidationError(f"{rule_label}: 'commands[{cmd_idx}]' array cannot be empty")
            for part_idx, part in enumerate(cmd):
                if not isinstance(part, str):
                    raise ValidationError(
                        f"{rule_label}: 'commands[{cmd_idx}][{part_idx}]' must be string, "
                        f"got {type(part).__name__}"
                    )
                if not part.strip():
                    raise ValidationError(f"{rule_label}: 'commands[{cmd_idx}][{part_idx}]' cannot be empty")
        else:
            raise ValidationError(
                f"{rule_label}: 'commands[{cmd_idx}]' must be string or array, "
                f"got {type(cmd).__name__}"
            )


__all__ = ["validate_dispatch_rules", "ValidationError"]
