"""FastAPI application exposing the admin dashboard."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import schedule_manager as sm

from .config import AppConfig, get_config
from .security import require_user


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Daily Manna Dashboard")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

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
        end = start + dt.timedelta(days=6)
        changed = sm.ensure_date_range(schedule, start, end)
        if changed:
            sm.save_schedule(schedule, schedule_path)

        entries = [schedule.get_entry(start + dt.timedelta(days=offset)) for offset in range(7)]

        context = {
            "entries": entries,
            "schedule_path": schedule_path,
            "start": start,
            "end": end,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
        return templates.TemplateResponse(request, "dashboard.html", context)

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
                sm.parse_selector(selector)
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


app = create_app()
