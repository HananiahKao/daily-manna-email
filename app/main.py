"""FastAPI application exposing the admin dashboard."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional
from urllib.parse import urlencode
import os
import json
import requests
import asyncio

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import secrets
from pydantic import BaseModel, field_validator
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Ensure modules at the repo root (e.g. schedule_manager) remain importable when uvicorn sets --app-dir
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import schedule_manager as sm
import content_source_factory
import job_dispatcher

from app.config import AppConfig, get_config
from app.security import require_user, authenticate_user, login_required, require_user_or_redirect
from app.oauth_scopes import get_scopes_descriptions
from app.cron_runner import get_cron_runner, shutdown_cron_runner
from app.caffeine_mode import start_caffeine_mode


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


class EntryPayload(BaseModel):
    date: dt.date
    selector: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    override: Optional[str] = None

    @field_validator("selector")
    @classmethod
    def _validate_selector(cls, value: Optional[str]) -> Optional[str]:
        if value:
            source = content_source_factory.get_active_source()
            source.parse_selector(value)
        return value

    @field_validator("status")
    @classmethod
    def _normalize_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("notes", "override", mode="before")
    @classmethod
    def _stringify_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class EntryMovePayload(BaseModel):
    new_date: dt.date


class MultiMovePayload(BaseModel):
    source_dates: List[dt.date]
    target_date: dt.date

    @field_validator("source_dates")
    @classmethod
    def _ensure_sources(cls, value: List[dt.date]) -> List[dt.date]:
        if not value:
            raise ValueError("source_dates cannot be empty")
        seen: Dict[dt.date, None] = {}
        for item in value:
            seen.setdefault(item, None)
        return list(seen.keys())


class BatchUpdatePayload(BaseModel):
    entries: List[EntryPayload]

    @field_validator("entries")
    @classmethod
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


class DispatchRulePayload(BaseModel):
    time: Optional[str] = None
    days: Optional[List[str | int]] = None

    @field_validator("time")
    @classmethod
    def _normalize_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return job_dispatcher.normalize_time_str(value)

    @field_validator("days")
    @classmethod
    def _normalize_days(cls, value: Optional[List[str | int]]) -> Optional[List[str | int]]:
        if value is None:
            return None
        
        # Validate and normalize days
        normalized = []
        for day in value:
            if isinstance(day, str):
                day_str = day.strip().lower()
                if day_str == "daily":
                    return ["daily"]
                raise ValueError(f"Invalid weekday: {day} (must be 0-6 or 'daily')")
            elif isinstance(day, int):
                if not 0 <= day <= 6:
                    raise ValueError(f"Invalid weekday: {day} (must be 0-6)")
                normalized.append(day)
            else:
                raise ValueError(f"Invalid weekday type: {type(day)}")
        
        # Remove duplicates and sort
        normalized = sorted(list(set(normalized)))
        
        # If all days selected, return ["daily"]
        if len(normalized) == 7:
            return ["daily"]
        
        return normalized


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
    app = FastAPI(title="Daily Manna Email")

    # Add session middleware
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Add function to template globals
    templates.env.globals['git_last_modified_date'] = git_last_modified_date

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/caffeine")
    def caffeine() -> JSONResponse:
        """Caffeine mode endpoint to prevent server from sleeping."""
        return JSONResponse({"status": "awake", "message": "Server is awake and active"})

    @app.get("/api/caffeine-status")
    def caffeine_status(settings: AppConfig = Depends(get_config)) -> JSONResponse:
        """Get caffeine mode status."""
        return JSONResponse({
            "enabled": settings.caffeine_mode,
            "message": "Caffeine mode is active" if settings.caffeine_mode else "Caffeine mode is inactive",
            "interval": settings.caffeine_interval
        })

    @app.get("/privacy-policy", response_class=HTMLResponse)
    def privacy_policy(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "privacy_policy.html")

    @app.get("/terms-of-service", response_class=HTMLResponse)
    def terms_of_service(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "terms_of_service.html")

    @app.get("/", name="root")
    def root(request: Request) -> Response:
        """Root route - show public home page."""
        templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
        return templates.TemplateResponse(request, "home.html")

    @app.get("/login-form", response_class=HTMLResponse)
    def login_page(request: Request) -> HTMLResponse:
        """Show login form."""
        templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
        return templates.TemplateResponse(request, "login.html", {
            "next": request.query_params.get("next", "/dashboard")
        })

    @app.post("/login")
    def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next: str = Form("/dashboard"),
    ) -> Response:
        if authenticate_user(username, password):
            request.session["user"] = username
            return RedirectResponse(url=next, status_code=status.HTTP_302_FOUND)
        else:
            templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid credentials", "next": next},
                status_code=status.HTTP_401_UNAUTHORIZED
            )

    @app.post("/logout")
    def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    @app.get("/oauth/status", response_class=JSONResponse)
    def oauth_status(_: str = Depends(require_user)) -> JSONResponse:
        """Check OAuth token status and scope information using Google tokeninfo API."""
        token_path = PROJECT_ROOT / "token.json"
        required_scopes = {
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.readonly'
        }

        try:
            if not token_path.exists():
                return JSONResponse({
                    "authorized": False,
                    "status": "unauthorized",
                    "message": "No OAuth tokens found",
                    "scope_status": "none"
                })

            # Load credentials from file (handles both encrypted and unencrypted)
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), scopes=None)
            except (ValueError, json.decoder.JSONDecodeError):
                # Try loading encrypted tokens
                try:
                    from app.token_encryption import decrypt_token_data, is_encrypted_data
                    with open(token_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    if is_encrypted_data(content):
                        decrypted_data = decrypt_token_data(content)
                        creds = Credentials.from_authorized_user_info(decrypted_data, scopes=None)
                    else:
                        raise ValueError("Not encrypted data")
                except Exception:
                    return JSONResponse({
                        "authorized": False,
                        "status": "corrupted",
                        "message": "OAuth token file is corrupted or unreadable",
                        "scope_status": "unknown"
                    })

            if not creds.token:
                return JSONResponse({
                    "authorized": False,
                    "status": "invalid",
                    "message": "No access token found in credentials",
                    "scope_status": "unknown"
                })

            # Always use stored scopes for analysis, but prefer tokeninfo if available
            granted_scopes = set(creds.scopes or [])  # Start with stored scopes

            # Query Google tokeninfo API for authoritative validation (optional)
            # This may fail for various reasons, but we still analyze stored scopes
            try:
                tokeninfo_url = f"https://oauth2.googleapis.com/tokeninfo?access_token={creds.token}"
                response = requests.get(tokeninfo_url, timeout=10)
                if response.status_code == 200:
                    tokeninfo_data = response.json()
                    # Parse granted scopes from tokeninfo response (most accurate)
                    scope_str = tokeninfo_data.get("scope", "")
                    if scope_str:
                        granted_scopes = set(scope_str.split())
            except requests.exceptions.RequestException:
                # If tokeninfo fails, use stored scopes
                pass

            # Determine scope status
            extra_scopes = set()
            missing_scopes = set()
            available_features = []
            disabled_features = []

            if granted_scopes == required_scopes:
                scope_status = "exact"
                available_features = ["Email sending", "Schedule replies"]
            elif required_scopes.issubset(granted_scopes):
                scope_status = "over-authorized"
                extra_scopes = granted_scopes - required_scopes
                available_features = ["Email sending", "Schedule replies"]
            else:
                scope_status = "partial"
                missing_scopes = required_scopes - granted_scopes
                # Determine which features are available based on granted scopes
                if 'https://www.googleapis.com/auth/gmail.send' in granted_scopes:
                    available_features.append("Email sending")
                else:
                    disabled_features.append("Email sending")

                if 'https://www.googleapis.com/auth/gmail.readonly' in granted_scopes:
                    available_features.append("Schedule replies")
                else:
                    disabled_features.append("Schedule replies")

            response_data = {
                "authorized": True,
                "status": "authorized",
                "message": "OAuth tokens valid",
                "scope_status": scope_status,
                "available_features": available_features,
                "disabled_features": disabled_features
            }

            if scope_status == "over-authorized":
                response_data["extra_scopes"] = list(extra_scopes)
                response_data["extra_scopes_descriptions"] = get_scopes_descriptions(list(extra_scopes))
                response_data["message"] = "OAuth tokens valid with additional permissions"
            elif scope_status == "partial":
                response_data["missing_scopes"] = list(missing_scopes)
                response_data["missing_scopes_descriptions"] = get_scopes_descriptions(list(missing_scopes))
                response_data["message"] = "OAuth tokens valid with partial permissions - some features disabled"

            return JSONResponse(response_data)

        except requests.exceptions.RequestException as e:
            return JSONResponse({
                "authorized": False,
                "status": "error",
                "message": f"Network error checking token status: {str(e)}",
                "scope_status": "unknown"
            })
        except Exception as e:
            return JSONResponse({
                "authorized": False,
                "status": "error",
                "message": f"Error checking OAuth status: {str(e)}",
                "scope_status": "unknown"
            })

    @app.get("/oauth/start")
    def oauth_start(request: Request) -> RedirectResponse:
        """Initiate OAuth flow."""
        require_user_or_redirect(request)
        client_secret_path = PROJECT_ROOT / "client_secret.json"
        if not client_secret_path.exists():
            return RedirectResponse(
                url=f"/dashboard?error=OAuth client secret not found. Please upload client_secret.json",
                status_code=status.HTTP_302_FOUND
            )

        try:
            flow = Flow.from_client_secrets_file(
                str(client_secret_path),
                scopes=[
                    'https://www.googleapis.com/auth/gmail.send',
                    'https://www.googleapis.com/auth/gmail.readonly'
                ],
                redirect_uri=request.url_for('oauth_callback')
            )

            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )

            # Store state in session for CSRF protection
            request.session['oauth_state'] = state

            return RedirectResponse(url=authorization_url)
        except Exception as e:
            return RedirectResponse(
                url=f"/dashboard?error=Failed to start OAuth flow: {str(e)}",
                status_code=status.HTTP_302_FOUND
            )

    @app.get("/oauth/callback")
    def oauth_callback(
        request: Request,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None
    ) -> RedirectResponse:
        """Handle OAuth callback."""
        require_user_or_redirect(request)

        # Check if user denied authorization
        if error == "access_denied":
            # Clear state from session
            request.session.pop('oauth_state', None)
            return RedirectResponse(
                url="/dashboard?error=Authorization was denied. Please try again if you want to grant access.",
                status_code=status.HTTP_302_FOUND
            )

        # Verify we have required parameters for successful authorization
        if not code or not state:
            return RedirectResponse(
                url="/dashboard?error=Missing authorization parameters",
                status_code=status.HTTP_302_FOUND
            )

        # Verify state for CSRF protection
        stored_state = request.session.get('oauth_state')
        if not stored_state or state != stored_state:
            return RedirectResponse(
                url="/dashboard?error=OAuth state mismatch - possible CSRF attack",
                status_code=status.HTTP_302_FOUND
            )

        client_secret_path = PROJECT_ROOT / "client_secret.json"
        if not client_secret_path.exists():
            return RedirectResponse(
                url="/dashboard?error=OAuth client secret not found",
                status_code=status.HTTP_302_FOUND
            )

        # Determine granted scopes from the callback URL
        granted_scopes = []
        if 'scope' in request.query_params:
            scope_param = request.query_params['scope']
            granted_scopes = scope_param.split()

        print(f"DEBUG: OAuth callback - code: {code[:10]}..., granted_scopes: {granted_scopes}")

        # Create flow with the actually granted scopes to avoid validation errors
        flow = Flow.from_client_secrets_file(
            str(client_secret_path),
            scopes=granted_scopes if granted_scopes else [
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.readonly'
            ],
            redirect_uri=request.url_for('oauth_callback')
        )

        creds = None
        scope_changed = len(granted_scopes) < 2  # Changed if we didn't get both required scopes

        print(f"DEBUG: Created flow with scopes: {granted_scopes}")

        try:
            # Use the authorization code to fetch tokens
            flow.fetch_token(code=code)
            creds = flow.credentials
            print(f"DEBUG: Successfully fetched tokens, creds.scopes: {creds.scopes if creds else 'None'}")
        except Exception as e:
            error_msg = str(e)
            # Debug: print the actual error message
            print(f"DEBUG: OAuth callback error: {error_msg}")
            print(f"DEBUG: Trying to get credentials after error...")
            try:
                creds = flow.credentials
                print(f"DEBUG: Got credentials after error: {creds.scopes if creds else 'None'}")
            except Exception as inner_e:
                print(f"DEBUG: Could not get credentials: {inner_e}")

            if not creds:
                return RedirectResponse(
                    url=f"/dashboard?error=OAuth authorization failed: {error_msg}",
                    status_code=status.HTTP_302_FOUND
                )

        # Store credentials if available
        if creds:
            # Import the encryption utilities
            try:
                from app.token_encryption import encrypt_token_data
                # Convert credentials to dict and encrypt
                creds_dict = json.loads(creds.to_json())
                encrypted_data = encrypt_token_data(creds_dict)
                token_path = PROJECT_ROOT / "token.json"
                with open(token_path, 'w', encoding='utf-8') as token_file:
                    token_file.write(encrypted_data)
                print(f"Saved encrypted credentials with scopes: {creds.scopes}")
            except ImportError:
                # Fallback to unencrypted if encryption not available
                print("WARNING: Token encryption not available, saving unencrypted")
                token_path = PROJECT_ROOT / "token.json"
                with open(token_path, 'w', encoding='utf-8') as token_file:
                    token_file.write(creds.to_json())
                print(f"Saved unencrypted credentials with scopes: {creds.scopes}")

        # Clear state from session
        request.session.pop('oauth_state', None)

        if scope_changed:
            return RedirectResponse(
                url="/dashboard?error=Permissions granted did not match the request. Please try again.&action=manage_permissions",
                status_code=status.HTTP_302_FOUND
            )
        else:
            return RedirectResponse(
                url="/dashboard?message=OAuth authorization successful",
                status_code=status.HTTP_302_FOUND
            )

    @app.get("/dashboard", response_class=HTMLResponse, name="dashboard")
    def dashboard(
        request: Request,
        settings: AppConfig = Depends(get_config),
    ) -> HTMLResponse:
        require_user_or_redirect(request)
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

    @app.get("/api/content-sources", response_class=JSONResponse)
    def api_content_sources(
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get available content sources."""
        return JSONResponse({
            "sources": content_source_factory.get_available_sources()
        })

    @app.get("/api/month", response_class=JSONResponse)
    def api_month(
        request: Request,
        year: Optional[int] = None,
        month: Optional[int] = None,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        content_source = request.headers.get("X-Content-Source")
        schedule_path = _resolve_schedule_path(settings, content_source)
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
        request: Request,
        start_date: Optional[str] = None,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        content_source = request.headers.get("X-Content-Source")
        schedule_path = _resolve_schedule_path(settings, content_source)
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
        request: Request,
        payload: EntryPayload,
        _: str = Depends(require_user),
        settings: AppConfig = Depends(get_config),
    ) -> JSONResponse:
        content_source = request.headers.get("X-Content-Source")
        schedule_path = _resolve_schedule_path(settings, content_source)
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
        request: Request,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get UI configuration for batch editing based on active content source."""
        content_source = request.headers.get("X-Content-Source")
        if content_source:
            source = content_source_factory.get_content_source(content_source)
        else:
            source = content_source_factory.get_active_source()
        
        config = {
            "source_name": source.get_source_name(),
            "ui_config": source.get_batch_ui_config(),
        }
        
        return JSONResponse(config)

    @app.post("/api/batch-edit/parse-selectors", response_class=JSONResponse)
    def api_parse_batch_selectors(
        payload: BatchSelectorParsePayload,
        request: Request,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """
        Parse batch selector input using the active content source.

        Returns parsed selectors or error message.
        """
        content_source = request.headers.get("X-Content-Source")
        if content_source:
            source = content_source_factory.get_content_source(content_source)
        else:
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

    @app.get("/api/dispatch-rules", response_class=JSONResponse)
    def api_dispatch_rules(
        _: str = Depends(require_user),
    ) -> JSONResponse:
        config_path = _resolve_dispatch_config_path()
        rules = job_dispatcher.load_rules(config_path)
        payload = {
            "config_path": str(config_path),
            "timezone": sm.TZ_NAME,
            "rules": [
                {
                    "name": rule.name,
                    "time": f"{rule.time.hour:02d}:{rule.time.minute:02d}",
                    "weekdays": list(rule.weekdays),
                    "weekdays_label": rule.weekdays_label,
                }
                for rule in rules
            ],
        }
        return JSONResponse(payload)

    @app.post("/api/dispatch-rules/{rule_name}", response_class=JSONResponse)
    def api_update_dispatch_rule(
        rule_name: str,
        payload: DispatchRulePayload,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        config_path = _resolve_dispatch_config_path()
        rules = _load_dispatch_config(config_path)
        updated_rule: Optional[Dict[str, object]] = None
        for rule in rules:
            if rule.get("name") == rule_name:
                if payload.time is not None:
                    rule["time"] = payload.time
                if payload.days is not None:
                    rule["days"] = payload.days
                updated_rule = rule
                break

        if updated_rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch rule not found")

        _save_dispatch_config(config_path, rules)
        return JSONResponse({
            "name": updated_rule.get("name"),
            "time": updated_rule.get("time"),
            "days": updated_rule.get("days") or updated_rule.get("weekdays"),
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

    # Email Activity API endpoints
    @app.get("/api/jobs/recent", response_class=JSONResponse)
    def api_jobs_recent(
        job_name: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get recent job executions with pagination support."""
        from app.job_tracker import get_job_tracker
        tracker = get_job_tracker()
        
        # Validate parameters
        if limit < 1 or limit > 100:
            limit = 20
        if offset < 0:
            offset = 0

        executions = tracker.get_recent_executions(job_name, limit, offset)

        # Convert to dict format for JSON response
        result = []
        for execution in executions:
            exec_dict = execution.to_dict()
            # Add formatted duration
            if execution.duration_seconds:
                exec_dict["duration_formatted"] = f"{execution.duration_seconds:.1f}s"
            else:
                exec_dict["duration_formatted"] = None
            result.append(exec_dict)

        # Calculate pagination metadata
        total_count = len(tracker.get_recent_executions(job_name, limit=10000))  # Get total count
        has_more = (offset + limit) < total_count

        return JSONResponse({
            "executions": result,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total_count,
                "has_more": has_more
            }
        })

    @app.get("/api/jobs/stats", response_class=JSONResponse)
    def api_jobs_stats(
        job_name: Optional[str] = None,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get job execution statistics."""
        from app.job_tracker import get_job_tracker
        tracker = get_job_tracker()
        stats = tracker.get_job_stats(job_name)
        return JSONResponse(stats)

    @app.post("/api/jobs/run/{job_name}", response_class=JSONResponse)
    async def api_run_job_manually(
        job_name: str,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Manually trigger a job execution."""
        try:
            cron_runner = await get_cron_runner()
            result = await cron_runner.run_job_manually(job_name)
            if result:
                return JSONResponse({
                    "success": True,
                    "message": f"Job {job_name} triggered successfully",
                    "execution_id": f"{result.job_name}_{result.start_time.isoformat()}"
                })
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown job: {job_name}")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @app.get("/api/jobs/status", response_class=JSONResponse)
    async def api_scheduler_status(
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get scheduler status and upcoming jobs."""
        try:
            cron_runner = await get_cron_runner()
            status = cron_runner.get_scheduler_status()
            return JSONResponse(status)
        except Exception as e:
            return JSONResponse({
                "running": False,
                "error": str(e),
                "jobs": []
            })

    @app.get("/api/jobs/logs/{execution_id}", response_class=JSONResponse)
    def api_job_logs(
        execution_id: str,
        _: str = Depends(require_user),
    ) -> JSONResponse:
        """Get detailed logs for a specific job execution."""
        from app.job_tracker import get_job_tracker
        tracker = get_job_tracker()

        # Parse execution_id (format: job_name_timestamp)
        try:
            parts = execution_id.rsplit("_", 1)
            if len(parts) != 2:
                raise ValueError("Invalid execution ID format")
            job_name = parts[0]
            timestamp = parts[1]

            # Find the execution
            executions = tracker.get_recent_executions(job_name, 100)
            for execution in executions:
                if execution.start_time.isoformat() == timestamp:
                    return JSONResponse({
                        "execution": execution.to_dict(),
                        "logs": execution.logs
                    })

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid execution ID: {str(e)}")

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


def _resolve_schedule_path(settings: AppConfig, content_source: Optional[str] = None) -> Path:
    if settings.schedule_file:
        return settings.schedule_file
    if content_source:
        # Derive schedule file from content source
        filename = f"state/{content_source.lower()}_schedule.json"
        return (Path(os.getcwd()) / filename).resolve()
    return sm.get_schedule_path()


def _resolve_dispatch_config_path() -> Path:
    return job_dispatcher.DEFAULT_CONFIG_PATH


def _load_dispatch_config(config_path: Path) -> List[Dict[str, object]]:
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return job_dispatcher.default_rules_config()


def _save_dispatch_config(config_path: Path, rules: List[Dict[str, object]]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(rules, fh, ensure_ascii=False, indent=2)


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
    
    # Determine content source from schedule path
    schedule_filename = str(schedule_path)
    if "wix" in schedule_filename.lower():
        source = content_source_factory.get_content_source("wix")
    elif "stmn1" in schedule_filename.lower():
        source = content_source_factory.get_content_source("stmn1")
    elif "ezoe" in schedule_filename.lower():
        source = content_source_factory.get_content_source("ezoe")
    else:
        # Fallback to active source if filename doesn't match any known content source
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


# Add startup and shutdown events for cron runner
@app.on_event("startup")
async def startup_event():
    """Initialize cron runner and caffeine mode on app startup."""
    try:
        cron_runner = await get_cron_runner()
        # Cron runner starts automatically in get_cron_runner()
        
        # Start caffeine mode in background
        asyncio.create_task(start_caffeine_mode())
    except Exception as e:
        print(f"Warning: Failed to start background services: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown cron runner on app shutdown."""
    try:
        await shutdown_cron_runner()
    except Exception as e:
        print(f"Warning: Failed to shutdown cron runner: {e}")
