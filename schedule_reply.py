"""Utilities for managing schedule reply tokens and parsing email responses."""

from __future__ import annotations

import datetime as dt
import re
import secrets
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import schedule_manager as sm


DEFAULT_TOKEN_TTL_DAYS = 10
META_KEY = "reply_tokens"


class TokenError(ValueError):
    """Raised when a token cannot be resolved."""


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""


class ParseError(ValueError):
    """Raised when reply parsing fails."""


@dataclass
class ReplyToken:
    token: str
    date: dt.date
    selector: str
    summary_id: str
    issued_at: dt.datetime
    expires_at: dt.datetime

    def to_dict(self) -> Dict[str, str]:
        return {
            "date": self.date.isoformat(),
            "selector": self.selector,
            "summary_id": self.summary_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, token: str, data: Dict[str, str]) -> "ReplyToken":
        date_raw = data.get("date")
        selector = data.get("selector")
        summary_id = data.get("summary_id")
        issued_raw = data.get("issued_at")
        expires_raw = data.get("expires_at")
        if not date_raw or not selector or not summary_id or not issued_raw or not expires_raw:
            raise TokenError("token record incomplete")
        try:
            date = dt.date.fromisoformat(str(date_raw))
            issued_at = dt.datetime.fromisoformat(str(issued_raw))
            expires_at = dt.datetime.fromisoformat(str(expires_raw))
        except Exception as exc:  # pragma: no cover - defensive guard
            raise TokenError("token record malformed") from exc
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=sm.TAIWAN_TZ)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=sm.TAIWAN_TZ)
        if expires_at < issued_at:
            raise TokenError("token expiry precedes issuance")
        return cls(token=token, date=date, selector=str(selector), summary_id=str(summary_id), issued_at=issued_at, expires_at=expires_at)


@dataclass
class ReplyInstruction:
    token: str
    verb: str
    arguments: Dict[str, object] = field(default_factory=dict)
    source: str = ""


_COMMAND_LINE_PATTERN = re.compile(r"^\[(?P<token>[A-Za-z0-9]{6,32})\]\s*(?P<body>.*)$")
_REPLY_BREAK_PATTERN = re.compile(r"^on\s+.*\b(wrote|說):?\s*$", re.IGNORECASE)


def _ensure_store(schedule: sm.Schedule) -> Dict[str, object]:
    store = schedule.meta.setdefault(META_KEY, {})
    tokens = store.setdefault("tokens", {})
    if not isinstance(tokens, dict):
        store["tokens"] = {}
    return store


def _generate_token(existing: Dict[str, object]) -> str:
    while True:
        candidate = secrets.token_hex(4).upper()
        if candidate not in existing:
            return candidate


def issue_reply_tokens(
    schedule: sm.Schedule,
    entries: Iterable[sm.ScheduleEntry],
    summary_id: str,
    issued_at: Optional[dt.datetime] = None,
    ttl_days: int = DEFAULT_TOKEN_TTL_DAYS,
) -> List[ReplyToken]:
    issued_at = issued_at or dt.datetime.now(tz=sm.TAIWAN_TZ)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=sm.TAIWAN_TZ)
    expires_at = issued_at + dt.timedelta(days=max(1, ttl_days))
    store = _ensure_store(schedule)
    tokens_map: Dict[str, Dict[str, str]] = store["tokens"]  # type: ignore[assignment]
    created: List[ReplyToken] = []
    for entry in entries:
        date_str = entry.date.isoformat()
        stale = [tok for tok, payload in tokens_map.items() if isinstance(payload, dict) and payload.get("date") == date_str]
        for token in stale:
            tokens_map.pop(token, None)
        token = _generate_token(tokens_map)
        payload = ReplyToken(
            token=token,
            date=entry.date,
            selector=entry.selector,
            summary_id=summary_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        tokens_map[token] = payload.to_dict()
        created.append(payload)
    store["last_summary_id"] = summary_id
    store["last_issued_at"] = issued_at.isoformat()
    store["last_expires_at"] = expires_at.isoformat()
    return created


def get_reply_token(schedule: sm.Schedule, token: str, now: Optional[dt.datetime] = None) -> ReplyToken:
    store = schedule.meta.get(META_KEY)
    if not isinstance(store, dict):
        raise TokenError("no reply tokens recorded")
    tokens_map = store.get("tokens")
    if not isinstance(tokens_map, dict):
        raise TokenError("token store missing")
    data = tokens_map.get(token.upper())
    if not isinstance(data, dict):
        raise TokenError("unknown token")
    payload = ReplyToken.from_dict(token.upper(), data)
    reference = now or dt.datetime.now(tz=sm.TAIWAN_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=sm.TAIWAN_TZ)
    if payload.expires_at <= reference:
        raise TokenExpiredError("token expired")
    return payload


def remove_reply_token(schedule: sm.Schedule, token: str) -> None:
    store = schedule.meta.get(META_KEY)
    if not isinstance(store, dict):
        return
    tokens_map = store.get("tokens")
    if isinstance(tokens_map, dict):
        tokens_map.pop(token.upper(), None)


def purge_expired_tokens(schedule: sm.Schedule, now: Optional[dt.datetime] = None) -> int:
    reference = now or dt.datetime.now(tz=sm.TAIWAN_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=sm.TAIWAN_TZ)
    store = _ensure_store(schedule)
    tokens_map: Dict[str, Dict[str, str]] = store["tokens"]  # type: ignore[assignment]
    removed = 0
    for token in list(tokens_map.keys()):
        data = tokens_map.get(token)
        if not isinstance(data, dict):
            tokens_map.pop(token, None)
            removed += 1
            continue
        try:
            payload = ReplyToken.from_dict(token, data)
        except TokenError:
            tokens_map.pop(token, None)
            removed += 1
            continue
        if payload.expires_at <= reference:
            tokens_map.pop(token, None)
            removed += 1
    store["last_purge_at"] = reference.isoformat()
    return removed


def list_active_tokens(schedule: sm.Schedule, now: Optional[dt.datetime] = None) -> List[ReplyToken]:
    reference = now or dt.datetime.now(tz=sm.TAIWAN_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=sm.TAIWAN_TZ)
    store = schedule.meta.get(META_KEY, {})
    tokens_map = store.get("tokens", {}) if isinstance(store, dict) else {}
    active: List[ReplyToken] = []
    if isinstance(tokens_map, dict):
        for token, data in tokens_map.items():
            if not isinstance(data, dict):
                continue
            try:
                payload = ReplyToken.from_dict(token, data)
            except TokenError:
                continue
            if payload.expires_at > reference:
                active.append(payload)
    return sorted(active, key=lambda rt: (rt.date, rt.token))


def parse_reply_body(body: str) -> List[ReplyInstruction]:
    instructions: List[ReplyInstruction] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        if _REPLY_BREAK_PATTERN.match(stripped):
            break
        match = _COMMAND_LINE_PATTERN.match(stripped)
        if not match:
            continue
        token = match.group("token").upper()
        remainder = match.group("body").strip()
        if not remainder:
            raise ParseError(f"missing command for token {token}")
        parts = remainder.split(None, 1)
        verb = parts[0].lower()
        tail = parts[1].strip() if len(parts) > 1 else ""
        instruction = _parse_instruction(token, verb, tail, stripped)
        instructions.append(instruction)
    return instructions


def _parse_instruction(token: str, verb: str, tail: str, source: str) -> ReplyInstruction:
    if verb in {"keep", "ok"}:
        if tail:
            raise ParseError(f"keep does not accept extra text ({token})")
        return ReplyInstruction(token=token, verb="keep", source=source)
    if verb in {"skip", "omit"}:
        arguments: Dict[str, object] = {}
        if tail:
            arguments["reason"] = tail
        return ReplyInstruction(token=token, verb="skip", arguments=arguments, source=source)
    if verb in {"move", "reschedule", "resched", "date"}:
        if not tail:
            raise ParseError(f"move requires ISO date ({token})")
        try:
            target = dt.date.fromisoformat(tail)
        except ValueError as exc:
            raise ParseError(f"invalid ISO date '{tail}' for token {token}") from exc
        return ReplyInstruction(token=token, verb="move", arguments={"date": target}, source=source)
    if verb in {"override", "weekday"}:
        if not tail:
            raise ParseError(f"override requires descriptor ({token})")
        return ReplyInstruction(token=token, verb="override", arguments={"descriptor": tail}, source=source)
    if verb in {"selector", "sel"}:
        if not tail:
            raise ParseError(f"selector requires value ({token})")
        # Note: Selector validation is deferred to the content source when applied
        return ReplyInstruction(token=token, verb="selector", arguments={"selector": tail}, source=source)
    if verb in {"note", "notes", "comment"}:
        if not tail:
            raise ParseError(f"note requires content ({token})")
        return ReplyInstruction(token=token, verb="note", arguments={"note": tail}, source=source)
    if verb == "status":
        if not tail:
            raise ParseError(f"status requires value ({token})")
        return ReplyInstruction(token=token, verb="status", arguments={"status": tail}, source=source)
    raise ParseError(f"unrecognized action '{verb}' for token {token}")


__all__ = [
    "DEFAULT_TOKEN_TTL_DAYS",
    "META_KEY",
    "ParseError",
    "ReplyInstruction",
    "ReplyToken",
    "TokenError",
    "TokenExpiredError",
    "get_reply_token",
    "issue_reply_tokens",
    "list_active_tokens",
    "parse_reply_body",
    "purge_expired_tokens",
    "remove_reply_token",
]
