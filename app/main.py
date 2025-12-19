"""FastAPI application exposing the admin dashboard."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Ensure modules at the repo root (e.g. schedule_manager) remain importable when uvicorn sets --app-dir
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import schedule_manager as sm
import content_source_factory

from app.config import AppConfig, get_config
from app.security import require_user


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


class EntryPayload(BaseModel):
    date: dt.date
    selector: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    override: Optional[str] = None

    @validator("selector")
    def _validate_selector(cls, value: Optional[str]) -> Optional[str]:
        if value:
            source = content_source_factory.get_active_source()
            source.parse_selector(value)
        return value

    @validator("status")
    def _normalize_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @validator("notes", "override", pre=True)
    def _stringify_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class EntryMovePayload(BaseModel):
    new_date: dt.date


class MultiMovePayload(BaseModel):
    source_dates: List[dt.date]
    target_date: dt.date

    @validator("source_dates")
    def _ensure_sources(cls, value: List[dt.date]) -> List[dt.date]:
        if not value:
            raise ValueError("source_dates cannot be empty")
        seen: Dict[dt.date, None] = {}
        for item in value:
            seen.setdefault(item, None)
        return list(seen.keys())


class BatchUpdatePayload(BaseModel):
    entries: List[EntryPayload]

    @validator("entries")
    def _ensure_entries(cls, value: List[EntryPayload]) -> List[EntryPayload]:
        if not value:
            raise ValueError("entries cannot be empty")
        # Ensure dates are unique
        seen: Dict[dt.date, None] = {}
        for entry in value:
            seen.setdefault(entry.date, None)
        return value


class BatchSelectorParsePayload(BaseModel):
    input_text: str


def git_last_modified_date(file_path: str) -> str:
    """
    Get the last commit date for a file from Git, formatted as 'Month DD, YYYY'.

    Falls back to current date if Git is not available or file has no commits.
    """
    try:
        # Run git log command to get the last commit date
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ad', '--date=format:%B %d, %Y', '--', file_path],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        # Git not available or command failed
        pass

    # Fallback to current date if Git fails
    return dt.datetime.now().strftime("%B %d, %Y")


def create_app() -> FastAPI:
    app = FastAPI(title="Daily Manna Dashboard")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Add function to template globals
    templates.env.globals['git_last_modified_date'] = git_last_modified_date

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/privacy-policy", response_class=HTMLResponse)
    def privacy_policy(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "privacy_policy.html")

    @app.get("/terms-of-service", response_class=HTMLResponse)
    def terms_of_service(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "terms_of_service.html")

    @app.get("/", response_class=HTMLResponse, name="dashboard")
    def dashboard(
        request: Request,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> HTMLResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)

        today = sm.taipei_today()
        start = today - dt.timedelta(days=today.weekday())
        end = _ensure_week(schedule, start, schedule_path)

        context = {
            "schedule_path": schedule_path,
            "start": start,
            "end": end,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
        return templates.TemplateResponse(request, "dashboard.html", context)

    @app.get("/api/month", response_class=JSONResponse)
    def api_month(
        year: Optional[int] = None,
        month: Optional[int] = None,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)

        # Default to current month if not specified
        if year is None or month is None:
            today = sm.taipei_today()
            year = today.year
            month = today.month

        # Calculate month boundaries
        month_start = dt.date(year, month, 1)
        # Find first day of the calendar grid (previous Monday)
        calendar_start = month_start - dt.timedelta(days=month_start.weekday())
        # Find last day of the calendar grid (next Sunday after month end)
        month_end = _get_month_end(year, month)
        calendar_end = month_end + dt.timedelta(days=(6 - month_end.weekday()))

        entries = []
        current_date = calendar_start
        while current_date <= calendar_end:
            entry = schedule.get_entry(current_date)
            serialized = _serialize_entry(entry, current_date)
            # Add flag to indicate if this day belongs to the current month
            serialized["is_current_month"] = current_date.month == month
            entries.append(serialized)
            current_date += dt.timedelta(days=1)

        payload = {
            "year": year,
            "month": month,
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "calendar_start": calendar_start.isoformat(),
            "calendar_end": calendar_end.isoformat(),
            "entries": entries,
            "schedule_path": str(schedule_path),
        }
        return JSONResponse(payload)

    # Keep the old week endpoint for backward compatibility
    @app.get("/api/week", response_class=JSONResponse)
    def api_week(
        start_date: Optional[str] = None,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)
        start = _normalize_week_start(start_date)
        end = _ensure_week(schedule, start, schedule_path)
        entries = []
        for offset in range(7):
            day = start + dt.timedelta(days=offset)
            entries.append(_serialize_entry(schedule.get_entry(day), day))
        payload = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "entries": entries,
            "schedule_path": str(schedule_path),
        }
        return JSONResponse(payload)

    @app.post("/api/entry", response_class=JSONResponse)
    def api_upsert_entry(
        payload: EntryPayload,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)
        entry = schedule.get_entry(payload.date)
        created = False
        if not entry:
            if not payload.selector:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selector required for new entry")
            entry = sm.ScheduleEntry(date=payload.date, selector=payload.selector)
            schedule.upsert_entry(entry)
            created = True
        if payload.selector:
            entry.selector = payload.selector
        if payload.status:
            entry.status = payload.status
            if payload.status == "sent":
                entry.sent_at = dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat()
            else:
                entry.sent_at = None
        if payload.notes is not None:
            entry.notes = payload.notes
        if payload.override is not None:
            entry.override = payload.override.strip() or None
        sm.save_schedule(schedule, schedule_path)
        return JSONResponse({"entry": _serialize_entry(entry, entry.date), "created": created})

    @app.delete("/api/entry/{date}", response_class=JSONResponse)
    def api_delete_entry(
        date: dt.date,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)
        removed = schedule.remove_entry(date)
        if not removed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        sm.save_schedule(schedule, schedule_path)
        return JSONResponse({"deleted": True, "date": date.isoformat()})

    @app.post("/api/entry/{date}/move", response_class=JSONResponse)
    def api_move_entry(
        date: dt.date,
        payload: EntryMovePayload,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)
        entry = schedule.get_entry(date)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        existing = schedule.get_entry(payload.new_date)
        if existing and existing is not entry:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target date already has an entry")
        entry.date = payload.new_date
        schedule.entries.sort(key=lambda item: item.date)
        sm.save_schedule(schedule, schedule_path)
        return JSONResponse({"entry": _serialize_entry(entry, entry.date)})

    @app.post("/api/entries/move", response_class=JSONResponse)
    def api_move_entries(
        payload: MultiMovePayload,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)
        entry_map: Dict[dt.date, sm.ScheduleEntry] = {}
        for date_value in payload.source_dates:
            entry = schedule.get_entry(date_value)
            if not entry:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entry missing for {date_value.isoformat()}")
            entry_map[date_value] = entry

        sorted_sources = sorted(entry_map)
        earliest = sorted_sources[0]
        delta = payload.target_date - earliest

        target_map: Dict[dt.date, dt.date] = {}
        for source_date in sorted_sources:
            new_date = source_date + delta
            target_map[source_date] = new_date
            existing = schedule.get_entry(new_date)
            if existing and existing.date not in entry_map:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Target date {new_date.isoformat()} already has an entry",
                )

        for source_date, entry in entry_map.items():
            entry.date = target_map[source_date]

        schedule.entries.sort(key=lambda item: item.date)
        sm.save_schedule(schedule, schedule_path)
        moved_payload = [_serialize_entry(entry, entry.date) for entry in entry_map.values()]
        return JSONResponse({"entries": moved_payload})

    @app.post("/api/entries/batch", response_class=JSONResponse)
    def api_batch_update_entries(
        payload: BatchUpdatePayload,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)

        updated_entries = []
        for entry_payload in payload.entries:
            entry = schedule.get_entry(entry_payload.date)
            created = False

            # Create entry if it doesn't exist and we have a selector
            if not entry:
                if not entry_payload.selector:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Selector required for new entry on {entry_payload.date.isoformat()}"
                    )
                entry = sm.ScheduleEntry(date=entry_payload.date, selector=entry_payload.selector)
                schedule.upsert_entry(entry)
                created = True

            # Update fields (only modify non-None values)
            if entry_payload.selector is not None:
                entry.selector = entry_payload.selector
            if entry_payload.status is not None:
                entry.status = entry_payload.status
                if entry_payload.status == "sent":
                    entry.sent_at = dt.datetime.now(tz=sm.TAIWAN_TZ).isoformat()
                else:
                    entry.sent_at = None
            if entry_payload.notes is not None:
                entry.notes = entry_payload.notes
            if entry_payload.override is not None:
                entry.override = entry_payload.override.strip() or None

            updated_entries.append({
                "entry": _serialize_entry(entry, entry.date),
                "created": created
            })

        sm.save_schedule(schedule, schedule_path)
        return JSONResponse({"entries": updated_entries})

    @app.get("/api/batch-edit/config", response_class=JSONResponse)
    def api_batch_edit_config(
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get UI configuration for batch editing based on active content source."""
        source = content_source_factory.get_active_source()
        
        config = {
            "source_name": source.get_source_name(),
            "ui_config": source.get_batch_ui_config(),
        }
        
        return JSONResponse(config)

    @app.post("/api/batch-edit/parse-selectors", response_class=JSONResponse)
    def api_parse_batch_selectors(
        payload: BatchSelectorParsePayload,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """
        Parse batch selector input using the active content source.

        Returns parsed selectors or error message.
        """
        source = content_source_factory.get_active_source()

        try:
            selectors = source.parse_batch_selectors(payload.input_text)
            return JSONResponse({
                "success": True,
                "selectors": selectors,
                "count": len(selectors),
            })
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    @app.post("/api/entries/batch-delete", response_class=JSONResponse)
    def api_batch_delete_entries(
        dates: List[dt.date],
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        """
        Delete multiple schedule entries by dates.
        """
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)

        deleted_dates = []
        for date in dates:
            if schedule.remove_entry(date):
                deleted_dates.append(date)

        if not deleted_dates:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No entries found to delete")

        sm.save_schedule(schedule, schedule_path)
        return JSONResponse({
            "deleted": [d.isoformat() for d in deleted_dates],
            "count": len(deleted_dates)
        })


    @app.post("/actions/{date}")
    def handle_action(
        request: Request,
        date: str,
        action: str = Form(...),
        note: Optional[str] = Form(None),
        selector: Optional[str] = Form(None),
        status_value: Optional[str] = Form(None, alias="status"),
        override: Optional[str] = Form(None),
        move_date: Optional[str] = Form(None),
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> RedirectResponse:
        schedule_path = _resolve_schedule_path(settings)
        schedule = sm.load_schedule(schedule_path)

        try:
            target_date = dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date") from exc

        entry = schedule.get_entry(target_date)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        message: Optional[str] = None
        error: Optional[str] = None

        try:
            if action == "mark_sent":
                sm.mark_sent(schedule, target_date)
                message = f"Marked {target_date.isoformat()} as sent."
            elif action == "skip":
                entry.status = "skipped"
                if note:
                    entry.notes = _append_note(entry.notes, note)
                message = f"Marked {target_date.isoformat()} as skipped."
            elif action == "note":
                if not note:
                    raise ValueError("Note text is required")
                entry.notes = _append_note(entry.notes, note)
                message = f"Updated notes for {target_date.isoformat()}."
            elif action == "selector":
                if not selector:
                    raise ValueError("Selector value is required")
                source = content_source_factory.get_active_source()
                source.parse_selector(selector)
                entry.selector = selector
                message = f"Selector updated for {target_date.isoformat()}."
            elif action == "status":
                if not status_value:
                    raise ValueError("Status value is required")
                entry.status = status_value
                message = f"Status updated for {target_date.isoformat()}."
            elif action == "override_set":
                if not override:
                    raise ValueError("Override descriptor is required")
                entry.override = override
                message = f"Override set for {target_date.isoformat()}."
            elif action == "override_clear":
                entry.override = None
                message = f"Override cleared for {target_date.isoformat()}."
            elif action == "move":
                if not move_date:
                    raise ValueError("Target date is required")
                new_date = dt.date.fromisoformat(move_date)
                existing = schedule.get_entry(new_date)
                if existing and existing is not entry:
                    raise ValueError(f"Date {new_date.isoformat()} already has an entry")
                entry.date = new_date
                schedule.entries.sort(key=lambda item: item.date)
                message = f"Moved entry to {new_date.isoformat()}."
            else:
                raise ValueError(f"Unsupported action '{action}'")
            sm.save_schedule(schedule, schedule_path)
        except Exception as exc:
            error = str(exc)

        params = []
        if message and not error:
            params.append(("message", message))
        if error:
            params.append(("error", error))
        query = f"?{urlencode(params)}" if params else ""
        url = str(request.url_for("dashboard")) + query
        return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)

    return app


def _append_note(current: str, addition: str) -> str:
    addition = (addition or "").strip()
    if not addition:
        return current or ""
    existing = (current or "").strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} | {addition}"


def _resolve_schedule_path(settings: AppConfig) -> Path:
    if settings.schedule_file:
        return settings.schedule_file
    return sm.get_schedule_path()


def _serialize_entry(entry: Optional[sm.ScheduleEntry], date: dt.date) -> Dict[str, object]:
    base = {
        "date": date.isoformat(),
        "weekday": date.strftime("%A"),
        "weekday_short": date.strftime("%a"),
        "weekday_index": date.weekday(),
        "is_missing": entry is None,
    }
    if entry:
        base.update(
            {
                "selector": entry.selector,
                "status": entry.status,
                "sent_at": entry.sent_at,
                "notes": entry.notes or "",
                "override": entry.override,
            }
        )
    else:
        base.update({"selector": None, "status": None, "sent_at": None, "notes": "", "override": None})
    return base


def _normalize_week_start(value: Optional[str]) -> dt.date:
    if not value:
        today = sm.taipei_today()
        return today - dt.timedelta(days=today.weekday())
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid start date") from exc
    return parsed - dt.timedelta(days=parsed.weekday())


def _ensure_week(schedule: sm.Schedule, start: dt.date, schedule_path: Path) -> dt.date:
    end = start + dt.timedelta(days=6)
    source = content_source_factory.get_active_source()
    if sm.ensure_date_range(schedule, source, start, end):
        sm.save_schedule(schedule, schedule_path)
    return end


def _get_month_end(year: int, month: int) -> dt.date:
    """Get the last day of the specified month."""
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


app = create_app()
