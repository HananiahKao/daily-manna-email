"""Apply admin reply commands to the schedule state."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import schedule_manager as sm
import schedule_reply as sr


class ApplyError(Exception):
    """Raised when an instruction cannot be applied."""


@dataclass
class InstructionOutcome:
    token: str
    verb: str
    status: str
    message: str
    date: Optional[dt.date] = None


@dataclass
class ProcessResult:
    outcomes: List[InstructionOutcome] = field(default_factory=list)
    changed: bool = False

    @property
    def errors(self) -> List[InstructionOutcome]:
        return [item for item in self.outcomes if item.status == "error"]

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "outcomes": [
                {
                    "token": item.token,
                    "verb": item.verb,
                    "status": item.status,
                    "message": item.message,
                    "date": item.date.isoformat() if item.date else None,
                }
                for item in self.outcomes
            ],
        }


def process_email(schedule: sm.Schedule, body: str, now: Optional[dt.datetime] = None) -> ProcessResult:
    instructions = sr.parse_reply_body(body)
    return apply_instructions(schedule, instructions, now=now)


def apply_instructions(
    schedule: sm.Schedule,
    instructions: Sequence[sr.ReplyInstruction],
    now: Optional[dt.datetime] = None,
) -> ProcessResult:
    result = ProcessResult()
    for instruction in instructions:
        try:
            token_info = sr.get_reply_token(schedule, instruction.token, now=now)
        except sr.TokenExpiredError:
            result.outcomes.append(
                InstructionOutcome(
                    token=instruction.token,
                    verb=instruction.verb,
                    status="error",
                    message="token expired",
                )
            )
            continue
        except sr.TokenError as exc:
            result.outcomes.append(
                InstructionOutcome(
                    token=instruction.token,
                    verb=instruction.verb,
                    status="error",
                    message=str(exc),
                )
            )
            continue

        entry = schedule.get_entry(token_info.date)
        if not entry:
            result.outcomes.append(
                InstructionOutcome(
                    token=instruction.token,
                    verb=instruction.verb,
                    status="error",
                    message=f"no entry for {token_info.date.isoformat()}",
                    date=token_info.date,
                )
            )
            continue

        try:
            changed, message = _apply_instruction(schedule, entry, instruction, token_info)
        except ApplyError as exc:
            result.outcomes.append(
                InstructionOutcome(
                    token=instruction.token,
                    verb=instruction.verb,
                    status="error",
                    message=str(exc),
                    date=entry.date,
                )
            )
            continue

        status = "noop"
        if instruction.verb != "keep" and changed:
            status = "applied"
        elif instruction.verb != "keep" and not changed:
            status = "noop"

        sr.remove_reply_token(schedule, instruction.token)
        if changed and instruction.verb != "keep":
            result.changed = True

        result.outcomes.append(
            InstructionOutcome(
                token=instruction.token,
                verb=instruction.verb,
                status=status,
                message=message,
                date=entry.date,
            )
        )
    return result


def _apply_instruction(
    schedule: sm.Schedule,
    entry: sm.ScheduleEntry,
    instruction: sr.ReplyInstruction,
    token_info: sr.ReplyToken,
) -> tuple[bool, str]:
    verb = instruction.verb
    if verb == "keep":
        return False, "kept without changes"
    if verb == "skip":
        reason = str(instruction.arguments.get("reason", "")).strip()
        entry.status = "skipped"
        if reason:
            entry.notes = _append_note(entry.notes, reason)
        return True, "marked as skipped"
    if verb == "note":
        note_text = str(instruction.arguments.get("note", "")).strip()
        if not note_text:
            raise ApplyError("note text required")
        entry.notes = _append_note(entry.notes, note_text)
        return True, "updated notes"
    if verb == "selector":
        selector = str(instruction.arguments.get("selector", "")).strip()
        if not selector:
            raise ApplyError("selector value required")
        entry.selector = selector
        entry.status = entry.status or "pending"
        return True, f"selector updated to {selector}"
    if verb == "status":
        value = str(instruction.arguments.get("status", "")).strip()
        if not value:
            raise ApplyError("status value required")
        entry.status = value
        return True, f"status set to {value}"
    if verb == "override":
        descriptor = str(instruction.arguments.get("descriptor", "")).strip()
        if not descriptor:
            raise ApplyError("override descriptor required")
        entry.override = descriptor
        return True, f"override set to {descriptor}"
    if verb == "move":
        target_date = instruction.arguments.get("date")
        if not isinstance(target_date, dt.date):
            raise ApplyError("move requires ISO date")
        existing = schedule.get_entry(target_date)
        if existing and existing is not entry:
            raise ApplyError(f"date {target_date.isoformat()} already assigned to {existing.selector}")
        entry.date = target_date
        schedule.entries.sort(key=lambda item: item.date)
        return True, f"moved to {target_date.isoformat()}"

    raise ApplyError(f"unsupported verb '{verb}'")


def _append_note(current: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return current or ""
    existing = (current or "").strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} | {addition}"


__all__ = [
    "ApplyError",
    "InstructionOutcome",
    "ProcessResult",
    "apply_instructions",
    "process_email",
]

