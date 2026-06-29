# Daily Manna Email — Comprehensive Codebase Architecture Analysis

**Document Date:** May 30, 2026  
**Project:** Daily Manna Email - Automated Scripture Lesson Delivery System  
**Language:** Python 3.9+  
**Total Lines of Code:** ~8,000+ (excluding tests and dependencies)  
**Total Python Files:** 62 (project code only)

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [Architecture Patterns](#architecture-patterns)
4. [Core Module Breakdown](#core-module-breakdown)
5. [Component Interactions](#component-interactions)
6. [Data Flow Architecture](#data-flow-architecture)
7. [Web Application Architecture](#web-application-architecture)
8. [Database & Persistence Layer](#database--persistence-layer)
9. [API Endpoints & Interfaces](#api-endpoints--interfaces)
10. [Job Scheduling & Execution](#job-scheduling--execution)
11. [Content Source Abstraction](#content-source-abstraction)
12. [Testing Architecture](#testing-architecture)
13. [Configuration & Environment](#configuration--environment)
14. [Security Architecture](#security-architecture)
15. [Deployment Architecture](#deployment-architecture)
16. [Code Metrics & Statistics](#code-metrics--statistics)
17. [Design Patterns Identified](#design-patterns-identified)
18. [Key Design Decisions](#key-design-decisions)
19. [Dependencies & Technology Stack](#dependencies--technology-stack)
20. [Future Extensibility & Scalability](#future-extensibility--scalability)

---

## Executive Summary

The **Daily Manna Email** system is a sophisticated Python-based automation platform designed to deliver Biblical scripture lessons ("聖經之旅" - Scripture Journey) to email subscribers. The system combines several architectural paradigms:

- **Event-driven scheduling** with APScheduler and cron-based dispatching
- **Content abstraction** supporting multiple content sources (EZOe, Wix, Legacy)
- **Microservice-like separation** of concerns through independent Python modules
- **RESTful web interface** with FastAPI for administrative management
- **Stateful JSON persistence** for lightweight schedule management
- **OAuth2 integration** with Gmail API for secure email delivery
- **Horizontal job execution** with retry logic and tracking

The system handles **~4,700 lines of application code** organized into **root-level utilities** and a **FastAPI app module**, with comprehensive test coverage and deployment automation.

---

## System Overview

### High-Level Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                     DAILY MANNA EMAIL SYSTEM                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐         ┌─────────────────────────────┐  │
│  │   Cron / Cron    │────────▶│  Hybrid Dispatcher System   │  │
│  │   Job Runner     │         │  (job_dispatcher.py)        │  │
│  │ (APScheduler)    │         └─────────────────────────────┘  │
│  └──────────────────┘                      │                   │
│                                             │                   │
│           ┌────────────────────────────────┼────────────────────┐
│           │                                │                    │
│      ┌────▼────────┐     ┌──────────────┐ ▼  ┌────────────────┐│
│      │  Schedule   │────▶│  Email       │────▶│ Gmail API      ││
│      │  Manager    │     │  Delivery    │    │  OAuth Flow    ││
│      │             │     └──────────────┘    └────────────────┘│
│      └─────────────┘            │                                │
│           │                     │                                │
│           │                     ▼                                │
│           │         ┌──────────────────────┐                    │
│           │         │ Content Scraper      │                    │
│           │         │ - EZOe               │                    │
│           │         │ - Wix                │                    │
│           │         │ - Legacy (SJZL)      │                    │
│           │         └──────────────────────┘                    │
│           │                                                     │
│      ┌────▼─────────────────────────────────────────────────┐  │
│      │      Admin Reply Processing Pipeline                │  │
│      │  (schedule_reply_fetcher.py →                        │  │
│      │   schedule_reply_processor.py)                       │  │
│      └────┬─────────────────────────────────────────────────┘  │
│           │                                                     │
│      ┌────▼──────────────────┐                                 │
│      │  FastAPI Dashboard    │                                 │
│      │  - Authentication     │                                 │
│      │  - CRUD Operations    │                                 │
│      │  - Job Monitoring     │                                 │
│      │  - Calendar View      │                                 │
│      └───────────────────────┘                                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         State Persistence (JSON Files)                  │  │
│  │  - ezoe_schedule.json (canonical schedule)             │  │
│  │  - dispatch_state.json (dispatcher state)              │  │
│  │  - job_history.json (execution history)                │  │
│  │  - last_schedule_summary.html (weekly email)           │  │
│  │  - last_reply_results.json (reply processing results)  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Stakeholders & Interaction Points

| Stakeholder | Interaction | Primary Touchpoint |
|-------------|-------------|-------------------|
| **Daily Recipient** | Receives daily scripture emails | Gmail inbox |
| **Admin Maintainer** | Manages schedules via CLI & email replies | `schedule_tasks.py` CLI, reply processing |
| **Web Admin** | Interactive schedule management | FastAPI Dashboard (`app/main.py`) |
| **Automated Cron Jobs** | Trigger email sends and summaries | Bash scripts in `scripts/` directory |

---

## Architecture Patterns

### 1. **Factory Pattern - Content Source Abstraction**

**Location:** `content_source.py`, `content_source_factory.py`

The system implements the **Open/Closed Principle** by abstracting content sources behind a factory pattern:

```python
class ContentSource(ABC):
    @abstractmethod
    def get_daily_content(self, selector: str) -> ContentBlock
    @abstractmethod
    def validate_selector(self, selector: str) -> bool
    @abstractmethod
    def advance_selector(self, selector: str) -> str
```

**Implementations:**
- `EzoeContentSource` - Scrapes from ezoe.work (volume-lesson-day format)
- `WixContentSource` - Scrapes from Wix-hosted "Morning Revival" site
- `StmnlContentSource` - Legacy SJZL source fallback

**Benefits:** Easy to add new content sources without modifying core logic.

### 2. **Hybrid Job Dispatcher Pattern**

**Location:** `job_dispatcher.py`, `app/cron_runner.py`

Combines **scheduled cron execution** with **stateful job coordination**:

```text
Cron every 10 minutes
    ↓
Load dispatch rules (JSON config)
    ↓
Evaluate which jobs should run (based on Taiwan time + state)
    ↓
Execute via subprocess with env vars and tracking
    ↓
Update dispatch state to prevent duplicate runs
```

**Key Innovation:** Uses both **APScheduler** (app-level scheduling) and **external bash scripts** (cron-friendly CLI), allowing flexibility in deployment (containerized vs. traditional cron).

### 3. **State Machine Pattern - Schedule Entry Lifecycle**

**Location:** `schedule_manager.py`

Entries follow a state progression:

```text
pending ──→ sent
  ↓
  skipped
```

Metadata tracks:
- `sent_at` (ISO timestamp when marked as sent)
- `notes` (admin annotations)
- `override` (manual selector replacement)
- `status` (pending/sent/skipped only)

### 4. **Observer Pattern - Admin Reply Processing**

**Location:** `schedule_reply_processor.py`, `schedule_reply_fetcher.py`

The system polls Gmail API for admin replies and **applies transformations** to schedule state:

```text
Gmail inbox
    ↓ (Poll via Gmail API)
Reply fetcher
    ↓
Token parsing (extract [TOKEN] verb args)
    ↓
Instruction processor (modify schedule in-memory)
    ↓
JSON persistence
    ↓
Confirmation email
```

### 5. **Dependency Injection Pattern**

**Location:** `app/main.py`, `app/security.py`

FastAPI uses dependency injection for:
- **Authentication:** `require_user` dependency checks credentials
- **Configuration:** `AppConfig` singleton
- **Database sessions:** `get_db_session` context manager

### 6. **Singleton Pattern - Global State**

**Location:** `app/cron_runner.py`, `app/job_tracker.py`

Critical singletons:
- `get_cron_runner()` - Manages APScheduler lifecycle
- `get_job_tracker()` - Centralized job execution history
- `AppConfig` - Environment configuration cache

### 7. **Template Method Pattern - Email Rendering**

**Location:** `sjzl_daily_email.py`

Core algorithm (template):

1. Fetch content from source
2. Extract plain text and HTML
3. Wrap HTML with scoped CSS
4. Build multipart MIME message
5. Send via Gmail API

Each content source implements the content fetching step.

---

## Core Module Breakdown

### **A. Root-Level Modules (~4,700 lines)**

#### **1. schedule_manager.py** (400+ lines)
**Purpose:** Core schedule data model and persistence

**Key Classes:**
- `ScheduleEntry` - Dataclass representing a single send (date, selector, status, notes, override)
- `Schedule` - Collection manager with JSON I/O, entry lookup, timezone handling

**Key Responsibilities:**
- Load/save schedule from `state/ezoe_schedule.json`
- Handle Taiwan timezone conversions
- Provide entry lookup by date
- Track schedule metadata (version, creation time, etc.)
- Calculate next pending entry
- Support schedule rolling (advance selectors when needed)

**Key Methods:**
```python
def load() -> Schedule
def save(self) -> None
def get_entry(date: dt.date) -> Optional[ScheduleEntry]
def get_pending_entries(start: dt.date, end: dt.date) -> List[ScheduleEntry]
def ensure_week(start_date: dt.date, selector: str) -> None
def mark_sent(date: dt.date, sent_at: Optional[dt.datetime]) -> None
```

#### **2. schedule_tasks.py** (600+ lines)
**Purpose:** CLI interface for schedule operations and admin workflows

**Key CLI Commands:**
- `next-entry` - Determine what to send today (respects overrides)
- `mark-sent` - Mark a date as sent with timestamp
- `ensure-week` - Pre-populate upcoming week, generate summaries
- `apply-reply` - Process admin reply commands (move, skip, selector, note, override)

**Key Responsibilities:**
- Orchestrate schedule manager operations
- Issue reply tokens (short-lived, for security)
- Render HTML + plain-text weekly summaries
- Send weekly summaries via Gmail API
- Parse and apply admin commands

**Reply Token System:**
```python
def issue_reply_tokens(schedule: Schedule, start_date: dt.date, count: int) -> None
    # Generates 6-character alphanumeric tokens stored in schedule.meta["reply_tokens"]
    # Tokens are embedded in HTML summaries for admin use
```

#### **3. sjzl_daily_email.py** (800+ lines)
**Purpose:** Email composition and delivery engine

**Key Responsibilities:**
- Fetch lesson content (HTML + plain text)
- Wrap content with scoped CSS for email clients
- Compose multipart MIME messages
- Send via Gmail API using OAuth credentials
- Handle UTF-8 encoding and OpenCC conversion

**Key Functions:**
```python
def get_day_html(selector: str, base: str) -> str
    # Delegates to content source's scraper
    
def _wrap_email_html_with_css(html: str) -> str
    # Inlines CSS, adds DOCTYPE, meta tags
    
def send_email(
    to: str, subject: str, 
    body_text: str, body_html: str
) -> None
    # Sends multipart/alternative via Gmail API
```

**CSS Wrapping Process:**
1. Extract `<style>` and `<link>` CSS from content
2. Inline CSS into HTML elements
3. Wrap with email-safe HTML5 doctype
4. Add UTF-8 meta tag
5. Remove problematic elements (scripts, iframes)

#### **4. ezoe_week_scraper.py** (700+ lines)
**Purpose:** Scrapes EZOe.work lesson content

**Key Responsibilities:**
- Fetch lesson HTML from ezoe.work
- Navigate to specific day anchor (e.g., `#1_8` for 周三)
- Extract day section with headers
- Handle UTF-8 decoding
- Provide day label mappings
- Suggest next selector when day out of range

**Day Mapping:**
```python
DAY_LABELS = {
    1: "週一", 2: "週二", 3: "週三", 4: "週四",
    5: "週五", 6: "週六", 7: "主日"
}
```

**Anchor Format:**
Selector `2-1-3` → URL anchor `#1_8` (day 3 = index 8 in HTML)

#### **5. job_dispatcher.py** (450+ lines)
**Purpose:** Determines which jobs should run based on Taiwan time and configuration

**Key Data Structure:**
```python
@dataclass
class DispatchRule:
    name: str                              # "daily-send", "weekly-summary"
    time: dt.time                          # 06:00 (in Taiwan TZ)
    weekdays: Sequence[int]                # [0,1,2,3,4,5,6] for all days
    commands: Sequence[Sequence[str]]      # [["bash", "scripts/run_daily_stateful_ezoe.sh"]]
    env: Optional[Dict[str, str]] = None   # Job-specific env vars
```

**Key Functions:**
```python
def load_rules(path: Path) -> List[DispatchRule]
    # Load from JSON or return defaults
    
def get_jobs_to_run(
    rules: List[DispatchRule],
    now: dt.datetime,
    state: Dict,
    max_delay: dt.timedelta
) -> List[DispatchRule]
    # Returns rules that should execute (based on time + weekday + state)
    
def update_job_run_time(name: str, now: dt.datetime, state: Dict) -> None
    # Persist last run time to prevent duplicate execution
```

**Default Rules:**
- `daily-send` at 06:00 Taiwan time (every day)
- `weekly-summary` at 21:00 Taiwan time (Sundays only)

**State Management:**
```json
{
  "daily-send": "2026-05-30T06:00:00+08:00",
  "weekly-summary": "2026-05-25T21:00:00+08:00"
}
```

#### **6. content_source.py** (125 lines)
**Purpose:** Abstract interface for content providers

**Abstract Methods:**
```python
class ContentSource(ABC):
    def get_daily_content(selector: str) -> ContentBlock
    def validate_selector(selector: str) -> bool
    def advance_selector(selector: str) -> str
    def parse_batch_selectors(input_text: str) -> List[str]
    def get_batch_ui_config() -> dict
```

**ContentBlock Data:**
```python
@dataclass
class ContentBlock:
    html_content: str
    plain_text_content: str
    title: str
```

#### **7. content_source_factory.py** (50+ lines)
**Purpose:** Factory for selecting content source based on environment

**Key Function:**
```python
def get_active_source() -> ContentSource
    # Returns EzoeContentSource, WixContentSource, or StmnlContentSource
    # based on CONTENT_SOURCE env var
```

#### **8. schedule_reply.py** (300+ lines)
**Purpose:** Token generation and reply parsing

**Key Functions:**
```python
def issue_reply_tokens(schedule: Schedule, start_date: dt.date, count: int) -> None
    # Generates 6-char tokens, stores in schedule.meta["reply_tokens"]
    
def parse_reply_body(body: str) -> List[Instruction]
    # Parses "[TOKEN] verb arg1 arg2" from email body
    
def validate_token(token: str, schedule: Schedule) -> bool
    # Checks if token exists and hasn't expired
```

**Supported Reply Verbs:**
- `keep` - Keep current selector
- `skip` - Skip this date (mark as skipped)
- `move <DATE>` - Reschedule to different date
- `selector <V-L-D>` - Change selector
- `note <TEXT>` - Add admin note
- `status <VALUE>` - Update status field
- `override <DESCRIPTOR>` - Set override field

#### **9. schedule_reply_processor.py** (300+ lines)
**Purpose:** Applies parsed instructions to schedule

**Key Function:**
```python
def apply_instructions(
    schedule: Schedule,
    instructions: List[Instruction],
    now: dt.datetime = None
) -> ProcessingResult
    # Modifies schedule entries based on instructions
    # Returns outcomes for confirmation email
```

**Outcome Types:**
- `success` - Instruction applied
- `invalid_token` - Token doesn't exist or expired
- `invalid_selector` - Selector failed validation
- `conflict` - Target date already has entry
- `parse_error` - Couldn't parse instruction

#### **10. schedule_reply_fetcher.py** (500+ lines)
**Purpose:** Polls Gmail API for admin replies, orchestrates processing

**Key Responsibilities:**
- Authenticate with Gmail API using OAuth credentials
- Query for unseen emails from allowed senders
- Extract plain-text body
- Delegate to reply processor
- Archive results to JSON
- Send confirmation emails

**Key Function:**
```python
def process_mailbox(
    schedule: Schedule,
    allowed_senders: List[str],
    dry_run: bool = False
) -> ProcessingResult
    # Main orchestration function
```

#### **11. oauth_utils.py** (300+ lines)
**Purpose:** OAuth2 authentication helpers

**Key Functions:**
```python
def get_gmail_service(use_cache: bool = True) -> service
    # Returns authenticated Gmail API client
    # Uses cached credentials when available
    
def refresh_oauth_token(creds: Credentials) -> Credentials
    # Refreshes expired OAuth token
```

#### **12. ezoe_content_source.py** (400+ lines)
**Purpose:** Concrete implementation for EZOe content source

**Selector Format:** `volume-lesson-day` (e.g., `2-1-3`)

**Key Methods:**
```python
def get_daily_content(selector: str) -> ContentBlock
def validate_selector(selector: str) -> bool
def advance_selector(selector: str) -> str  # Increments day, rolls to next lesson/volume
def parse_batch_selectors(input_text: str) -> List[str]  # Supports "2-1-1 to 2-1-5" range syntax
```

#### **13. wix_content_source.py** (400+ lines)
**Purpose:** Concrete implementation for Wix-hosted content

**Selector Format:** Chinese weekday (e.g., `【週三】`)

**Key Methods:**
Similar to EzoeContentSource, but selector validation and advancement differ.

#### **14. stmn1_content_source.py** (300+ lines)
**Purpose:** SJZL content source for remote deployment

**Note:** Used on remote servers where ezoe.work access is blocked by anti-bot detection. Provides same content as EZOe but from alternative source. Enabled via `CONTENT_SOURCE=stmn1` environment variable.

---

### **B. FastAPI Application Module** (3,300+ lines)

#### **1. app/main.py** (1,200+ lines)
**Purpose:** Core FastAPI application with routes, authentication, and CRUD operations

**Key Components:**

**Route Categories:**

| Category | Endpoints | Purpose |
|----------|-----------|---------|
| **Authentication** | `GET /login`, `POST /login` | Login page and form handling |
| **Dashboard** | `GET /`, `GET /dashboard` | Main admin dashboard |
| **API CRUD** | `POST /api/entries`, `PUT /api/entries/{date}` | Schedule entry management |
| **API Calendar** | `GET /api/calendar/month/{year}/{month}` | Monthly grid view |
| **API Batch Operations** | `POST /api/batch-update`, `POST /api/batch-parse` | Multi-entry updates |
| **Dispatch Rules** | `GET /api/dispatch-rules`, `PUT /api/dispatch-rules/{name}` | Job dispatcher config |
| **Job Status** | `GET /api/jobs/recent`, `GET /api/jobs/stats` | Execution history |

**Key Pydantic Models:**
```python
class EntryPayload(BaseModel):
    date: dt.date
    selector: Optional[str]
    status: Optional[str]
    notes: Optional[str]
    override: Optional[str]

class BatchUpdatePayload(BaseModel):
    entries: List[EntryPayload]

class DispatchRulePayload(BaseModel):
    time: Optional[str]
    days: Optional[List[str | int]]
```

**Authentication Flow:**
1. User submits credentials via form
2. `authenticate_user()` validates against `ADMIN_DASHBOARD_USER` / `ADMIN_DASHBOARD_PASSWORD` env vars
3. Session middleware (Starlette) stores authenticated user
4. `require_user` dependency checks session on protected routes

**Dashboard Features:**
- Weekly calendar grid with color-coded entry states
- Inline CRUD buttons (mark sent, skip, move, edit selector/notes)
- Flash messages for feedback
- Monthly navigation
- Job execution history sidebar

#### **2. app/security.py** (150+ lines)
**Purpose:** Authentication and authorization middleware

**Key Functions:**
```python
def require_user(request: Request) -> dict
    # Dependency that enforces authentication
    # Raises HTTPException 403 if not authenticated
    
def authenticate_user(username: str, password: str) -> bool
    # Checks credentials against env vars
```

**Session Middleware:**
Uses Starlette's `SessionMiddleware` with secret key from env.

#### **3. app/job_tracker.py** (400+ lines)
**Purpose:** Tracks job execution history and provides analytics

**Key Classes:**
```python
@dataclass
class JobExecutionResult:
    job_name: str
    start_time: dt.datetime
    end_time: Optional[dt.datetime]
    status: str  # running, success, failed, skipped
    exit_code: Optional[int]
    logs: List[str]
    retry_count: int
    error_message: Optional[str]

class JobTracker:
    def start_job(name: str) -> JobExecutionResult
    def update_job(result: JobExecutionResult) -> None
    def get_recent_executions(limit: int = 50) -> List[JobExecutionResult]
    def get_job_stats(job_name: Optional[str] = None) -> Dict[str, Any]
```

**Persistence:**
Stores history in `state/job_history.json` with automatic rotation/pruning.

#### **4. app/cron_runner.py** (600+ lines)
**Purpose:** Background job scheduler using APScheduler

**Key Class:**
```python
class CronJobRunner:
    async def start() -> None
        # Starts APScheduler with cron trigger (10-minute intervals)
    
    async def _run_dispatcher_trigger() -> None
        # Executes job dispatcher to determine which jobs to run
    
    async def _execute_job_from_rule(rule: DispatchRule) -> None
        # Executes a single job with subprocess and tracking
```

**Integration Points:**
- Reads dispatch rules from `config/dispatch_rules.json`
- Updates dispatcher state in `state/dispatch_state.json`
- Tracks execution in `state/job_history.json`
- Logs to `logs/cron_jobs.log`

**Retry Logic:**
```text
Attempt 1 (immediate)
  ↓ (failure)
Wait 1 minute
  ↓
Attempt 2
  ↓ (failure)
Wait 1 minute
  ↓
Attempt 3 (final)
  ↓
Mark as failed
```

#### **5. app/config.py** (200+ lines)
**Purpose:** Configuration management

**Key Class:**
```python
class AppConfig:
    admin_user: str = os.getenv("ADMIN_DASHBOARD_USER", "admin")
    admin_password: str = os.getenv("ADMIN_DASHBOARD_PASSWORD", "")
    content_source: str = os.getenv("CONTENT_SOURCE", "ezoe")
    smtp_user: str = os.getenv("SMTP_USER", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./daily_manna.db")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    secret_key: str = os.getenv("SECRET_KEY", "changeme")
```

**Initialization:**
```python
def get_config() -> AppConfig
    # Returns singleton config instance
```

#### **6. app/models.py** (85 lines)
**Purpose:** SQLAlchemy ORM models

**Key Model:**
```python
class Subscriber(Base):
    __tablename__ = "subscribers"
    
    id: int (primary key)
    email_encrypted: str  # AES-256-GCM encrypted
    content_source: str   # 'ezoe', 'wix'
    subscribed_at: datetime
    active: bool
```

**Key Features:**
- Email encryption at rest (AES-256-GCM)
- Per-source subscriber tracking
- Indexed by email and content_source for fast lookup

#### **7. app/database.py** (85 lines)
**Purpose:** Database initialization and session management

**Key Functions:**
```python
def init_database(database_url: str) -> None
    # Creates engine, initializes tables, creates session factory

def get_db_session() -> Session
    # Returns new database session
    # Must be used with context manager
```

**Database Support:**
- SQLite (development)
- PostgreSQL (production)

#### **8. app/email_encryption.py** (200+ lines)
**Purpose:** Encryption utilities for sensitive email data

**Key Functions:**
```python
def encrypt_email(email: str, key: bytes) -> str
    # AES-256-GCM encryption with IV

def decrypt_email(encrypted: str, key: bytes) -> str
    # AES-256-GCM decryption
```

#### **9. app/token_encryption.py** (200+ lines)
**Purpose:** OAuth token encryption for secure storage

**Key Functions:**
```python
def encrypt_credentials(creds: Credentials, key: bytes) -> str
    # Serializes and encrypts Google OAuth credentials

def decrypt_credentials(encrypted: str, key: bytes) -> Credentials
    # Decrypts and deserializes OAuth credentials
```

#### **10. app/oauth_scopes.py** (50+ lines)
**Purpose:** Gmail API scope definitions and descriptions

**Key Scopes:**
- `gmail.send` - Send emails
- `gmail.readonly` - Read Gmail (for reply processing)
- `gmail.modify` - Modify Gmail (mark as read)

#### **11. app/subscriber_manager.py** (300+ lines)
**Purpose:** Subscriber CRUD operations

**Key Functions:**
```python
def add_subscriber(email: str, content_source: str) -> Subscriber
def remove_subscriber(email: str) -> bool
def get_subscribers(content_source: str) -> List[Subscriber]
def is_subscribed(email: str, content_source: str) -> bool
```

#### **12. app/caffeine_mode.py** (400+ lines)
**Purpose:** High-frequency polling mode for rapid iteration

**Key Features:**
- Runs jobs every minute instead of standard intervals
- Useful for testing and rapid development
- Can be enabled/disabled via env var

---

### **C. Scripts Directory** (600+ lines)

#### **1. scripts/run_daily_stateful_ezoe.sh**
**Purpose:** Wrapper for daily email send

**Steps:**
1. Source `.env`
2. Query next selector via `schedule_tasks.py next-entry`
3. Export `EZOE_SELECTOR`
4. Execute `sjzl_daily_email.py`
5. Mark date as sent via `schedule_tasks.py mark-sent`

**Error Handling:**
- Exit early if date already marked sent (unless `RUN_FORCE=1`)
- Log all output to file

#### **2. scripts/run_weekly_schedule_summary.sh**
**Purpose:** Generate and email weekly summary

**Steps:**
1. Ensure upcoming week exists via `schedule_tasks.py ensure-week`
2. Generate HTML + plain-text summary
3. Archive summary to `state/last_schedule_summary.html`
4. Email to `ADMIN_SUMMARY_TO` if configured
5. Include reply tokens in summary

#### **3. scripts/run_schedule_reply_processor.sh**
**Purpose:** Process admin replies from Gmail

**Steps:**
1. Source `.env`
2. Execute `scripts/process_schedule_replies.py`
3. Handles `--limit`, `--dry-run` flags

#### **4. scripts/process_schedule_replies.py**
**Purpose:** CLI entry point for reply processing

**Key Arguments:**
```text
--limit N          Process up to N emails
--dry-run          Show what would happen without modifying state
--input FILE       Read from file instead of Gmail
```

#### **5. scripts/run_dispatcher.sh**
**Purpose:** Wrapper for job dispatcher

Activates virtualenv and sources `.env` before running `job_dispatcher.py`.

---

### **D. Static Files & Templates**

#### **Templates (Jinja2)**

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout with navigation, footer |
| `dashboard.html` | Weekly calendar grid, entry editor |
| `home.html` | Landing page with authentication form |
| `login.html` | Login form |
| `privacy_policy.html` | Privacy policy page |
| `terms_of_service.html` | Terms of service page |

**Key Features:**
- Responsive design (mobile-friendly)
- Real-time calendar grid loading via JavaScript
- Inline form actions with AJAX
- Flash message display

#### **Static Files (JavaScript)**

| File | Purpose |
|------|---------|
| `calendar.js` | Calendar grid navigation and rendering |
| `dispatch_rules.js` | Dispatch rule configuration UI |
| `caffeine_mode.js` | Toggle caffeine mode |
| `style.css` | Application styling |

---

## Component Interactions

### **Daily Email Send Workflow**

```text
Cron runs every 10 minutes
    ↓
APScheduler triggers dispatcher
    ↓
job_dispatcher.py:get_jobs_to_run()
    ↓
Check if current time matches "daily-send" rule (06:00)
    ↓
Check dispatch state - has rule run in current time window?
    ↓
YES: Execute ["bash", "scripts/run_daily_stateful_ezoe.sh"]
    ↓
Script sources .env
    ↓
schedule_tasks.py next-entry
    ├─ Load schedule from state/ezoe_schedule.json
    ├─ Check EZOE_SEND_WEEKDAY override (if set)
    ├─ Check EZOE_SEND_DATE override (if set)
    ├─ Find next pending entry
    └─ Export EZOE_SELECTOR
    ↓
sjzl_daily_email.py
    ├─ content_source_factory.get_active_source()
    ├─ ContentSource.get_daily_content(EZOE_SELECTOR)
    ├─ sjzl_daily_email.get_day_html() if EZOE_SELECTOR set
    │   └─ ezoe_week_scraper.get_day_html()
    │       ├─ Fetch from ezoe.work
    │       ├─ Parse HTML, find day section
    │       └─ Return extracted HTML + plain text
    ├─ _wrap_email_html_with_css()
    ├─ build_multipart_message()
    ├─ send_email() via Gmail API
    └─ Return success/failure
    ↓
schedule_tasks.py mark-sent --date TODAY
    ├─ Load schedule
    ├─ Update entry status to "sent"
    ├─ Save to state/ezoe_schedule.json
    └─ Return success
    ↓
Script logs results
    ↓
job_tracker records execution in state/job_history.json
    ↓
Dashboard displays job status
```

### **Weekly Summary & Reply Processing Workflow**

```text
Cron runs Sunday at 21:00 Taiwan time
    ↓
APScheduler triggers dispatcher
    ↓
job_dispatcher detects "weekly-summary" rule match
    ↓
Execute scripts/run_weekly_schedule_summary.sh
    ↓
schedule_tasks.py ensure-week --email
    ├─ Load schedule
    ├─ Check if week starting Monday exists
    ├─ If not, create entries using EZOE_VOLUME/LESSON/DAY_START seed
    ├─ issue_reply_tokens() - generate 6-char alphanumeric tokens
    ├─ Render HTML + plain-text summaries with token column
    ├─ Archive HTML to state/last_schedule_summary.html
    └─ send_email() to ADMIN_SUMMARY_TO distribution list
    ↓
Admin reviews email, sends reply like:
    "[ABC123] move 2026-06-03"
    "[ABC123] skip"
    "[ABC124] selector 2-2-1"
    ↓
Cron: scripts/run_schedule_reply_processor.sh --limit 5
    ↓
process_schedule_replies.py
    ├─ Authenticate with Gmail API
    ├─ Query unread emails from ADMIN_REPLY_FROM senders
    ├─ schedule_reply_fetcher.process_mailbox()
    │   ├─ Extract plain-text body
    │   ├─ schedule_reply.parse_reply_body()
    │   │   └─ Parse "[TOKEN] verb args" from text
    │   ├─ schedule_reply_processor.apply_instructions()
    │   │   ├─ Load schedule
    │   │   ├─ Validate token, selector, dates
    │   │   ├─ Apply each instruction (move, skip, selector, etc.)
    │   │   ├─ Persist updated schedule
    │   │   └─ Collect outcomes
    │   ├─ Archive results to state/last_reply_results.json
    │   ├─ Mark processed emails as read in Gmail
    │   └─ send_email() confirmation with outcomes
    └─ Return success
```

### **Admin Dashboard Interaction Workflow**

```text
Admin visits dashboard (http://localhost:8000)
    ↓
app/main.py:GET /
    ├─ Check authentication via require_user dependency
    ├─ If not authenticated: redirect to /login
    ├─ If authenticated: load schedule_manager.Schedule
    ├─ Determine current week boundaries
    ├─ Render dashboard.html with Jinja2
    └─ Return HTML
    ↓
Browser loads JavaScript (calendar.js)
    ↓
JavaScript: GET /api/calendar/month/{year}/{month}
    ├─ Return JSON grid with entry metadata
    └─ Render calendar cells with color codes
    ↓
Admin clicks "Mark Sent" button
    ↓
JavaScript: POST /handle-action
    ├─ Form data: action=mark_sent, date=YYYY-MM-DD
    ├─ FastAPI parses form
    ├─ schedule_manager.Schedule.mark_sent(date)
    ├─ Save updated schedule
    ├─ Create flash message
    └─ Redirect with message
    ↓
Admin sees "Entry marked as sent" confirmation
```

---

## Data Flow Architecture

### **Data Model (Schedule Entry)**

```python
@dataclass
class ScheduleEntry:
    date: dt.date                      # Send date
    selector: str                      # Content selector (e.g., "2-1-3")
    status: str = "pending"            # pending, sent, skip, error, archived
    sent_at: Optional[str] = None      # ISO timestamp when actually sent
    notes: str = ""                    # Admin annotations
    override: Optional[str] = None     # Manual override descriptor
    
class Schedule:
    entries: List[ScheduleEntry]       # Sorted by date (ascending)
    meta: Dict[str, Any]               # Metadata (version, reply_tokens, etc.)
    
    meta["reply_tokens"] = {
        "ABC123": {
            "issued_at": "2026-05-30T...",
            "entry_date": "2026-06-02",
            "expires_at": "2026-06-02T..."
        }
    }
```

### **JSON Persistence Layer**

#### **state/ezoe_schedule.json**
```json
{
  "version": 1,
  "created_at": "2026-01-01T00:00:00+08:00",
  "entries": [
    {
      "date": "2026-05-30",
      "selector": "2-1-3",
      "status": "sent",
      "sent_at": "2026-05-30T06:15:00+08:00",
      "notes": "Manual override applied",
      "override": null
    },
    {
      "date": "2026-05-31",
      "selector": "2-1-4",
      "status": "pending",
      "sent_at": null,
      "notes": "",
      "override": null
    }
  ],
  "meta": {
    "reply_tokens": {
      "ABC123": {
        "issued_at": "2026-05-30T21:00:00+08:00",
        "entry_date": "2026-06-01",
        "expires_at": "2026-06-02T00:00:00+08:00"
      }
    }
  }
}
```

#### **state/dispatch_state.json**
```json
{
  "daily-send": "2026-05-30T06:00:00+08:00",
  "weekly-summary": "2026-05-25T21:00:00+08:00"
}
```

#### **state/job_history.json**
```json
[
  {
    "job_name": "daily-send",
    "start_time": "2026-05-30T06:00:00+08:00",
    "end_time": "2026-05-30T06:02:15+08:00",
    "status": "success",
    "exit_code": 0,
    "logs": ["Script started", "Email sent to 50 recipients"],
    "retry_count": 0,
    "error_message": null
  }
]
```

#### **state/last_reply_results.json**
```json
{
  "processed_at": "2026-05-30T21:30:00+08:00",
  "total_emails": 5,
  "outcomes": {
    "ABC123": "success",
    "ABC124": "invalid_token",
    "ABC125": "success"
  },
  "errors": []
}
```

---

## Web Application Architecture

### **FastAPI Application Structure**

```text
app/
├── main.py                 # Core FastAPI app + routes
├── security.py             # Authentication middleware
├── config.py               # Configuration management
├── models.py               # SQLAlchemy ORM models
├── database.py             # Database initialization
├── job_tracker.py          # Job execution history
├── cron_runner.py          # APScheduler integration
├── email_encryption.py     # Email data encryption
├── token_encryption.py     # OAuth token encryption
├── oauth_scopes.py         # Gmail API scopes
├── subscriber_manager.py    # Subscriber CRUD
├── caffeine_mode.py        # High-frequency polling
├── templates/              # Jinja2 templates
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   ├── home.html
│   ├── privacy_policy.html
│   └── terms_of_service.html
└── static/                 # Static assets
    ├── style.css
    ├── calendar.js
    ├── dispatch_rules.js
    └── caffeine_mode.js
```

### **Request/Response Patterns**

**Authentication Flow:**

```text
GET /login (unauthenticated)
    ↓ [GET]
Response: login.html form

POST /login (form submission)
    ├─ Extract username, password from form
    ├─ Validate against env vars via authenticate_user()
    ├─ Create session (via SessionMiddleware)
    └─ Redirect: GET /dashboard

GET /dashboard (requires auth)
    ├─ require_user dependency checks session
    ├─ If invalid: raise HTTPException(status_code=403)
    └─ If valid: render dashboard.html
```

**API CRUD Pattern:**

```text
GET /api/entries/{date}
    └─ Returns: {"date": "...", "selector": "...", "status": "..."}

POST /api/entries
    ├─ Expects: {"date": "...", "selector": "...", ...}
    ├─ Creates new entry or updates existing
    └─ Returns: Updated entry

PUT /api/entries/{date}
    ├─ Updates specific fields
    └─ Returns: Updated entry

DELETE /api/entries/{date}
    ├─ Marks as archived or removes
    └─ Returns: 204 No Content
```

### **Frontend State Management**

**JavaScript Architecture:**
```text
browser
    ├─ calendar.js
    │   ├─ Fetch /api/calendar/month/{y}/{m}
    │   ├─ Render calendar grid
    │   └─ Attach event listeners
    ├─ dispatch_rules.js
    │   └─ Manage dispatch rule configuration UI
    └─ caffeine_mode.js
        └─ Toggle caffeine mode switch
```

**Client-Side Caching:**
- Calendar month data cached in memory
- Refresh on manual action completion
- No persistent storage (state authority is server)

---

## Database & Persistence Layer

### **Database Schema**

**SQLAlchemy Models:**

```python
class Subscriber(Base):
    __tablename__ = "subscribers"
    
    id: Integer (PK)
    email_encrypted: String (indexed)
    content_source: String (indexed) # 'ezoe', 'wix', 'stmn1'
    subscribed_at: DateTime (default: now)
    active: Boolean (default: True)
```

**Indexes:**
- `(email_encrypted, content_source)` - Composite unique index for subscriber lookup

### **Encryption Strategy**

**At-Rest Encryption:**
- Subscriber emails encrypted with AES-256-GCM
- OAuth tokens encrypted with AES-256-GCM
- Key stored in env var `ENCRYPTION_KEY` (base64-encoded)

**Encryption Flow:**
```text
Plain email
    ↓ (AES-256-GCM with random IV)
Ciphertext + IV (base64-encoded)
    ↓ (store in database)
Encrypted blob in DB
    ↓ (on retrieval)
Decrypt using ENCRYPTION_KEY
    ↓
Plain email in memory (for use only)
```

### **Database Support**

The system determines which database to use via the `DATABASE_MODE` environment variable, combined with `DATABASE_URL`:

```bash
DATABASE_MODE=sqlite       # or "postgres"/"postgresql"
DATABASE_URL=sqlite:///./daily_manna.db
```

| Mode | Database | URL Example |
|------|----------|-------------|
| `sqlite` | SQLite | `sqlite:///./daily_manna.db` |
| `postgres` / `postgresql` | PostgreSQL | `postgresql://user:pass@host/dbname` |

**Connection Pooling:**
- SQLite: `check_same_thread=False`
- PostgreSQL: Pool with `pool_recycle=300` (5-minute recycle)

---

## API Endpoints & Interfaces

### **Authentication Endpoints**

| Method | Path | Authentication | Purpose |
|--------|------|----------------|---------|
| GET | `/login` | None | Render login form |
| POST | `/login` | Form creds | Authenticate and create session |
| POST | `/logout` | Required | Clear session |

### **Dashboard & UI Endpoints**

| Method | Path | Authentication | Purpose |
|--------|------|----------------|---------|
| GET | `/` | None | Render public home page |
| GET | `/dashboard` | Required | Render admin dashboard (redirects if not authenticated) |
| GET | `/privacy-policy` | None | Privacy policy page |
| GET | `/terms-of-service` | None | Terms page |

### **Calendar & Scheduling Endpoints**

| Method | Path | Authentication | Purpose |
|--------|------|----------------|---------|
| GET | `/api/calendar/month/{year}/{month}` | Required | Get monthly grid with entries |
| GET | `/api/entries/{date}` | Required | Get single entry details |
| POST | `/api/entries` | Required | Create entry |
| PUT | `/api/entries/{date}` | Required | Update entry |
| DELETE | `/api/entries/{date}` | Required | Delete entry |
| POST | `/api/batch-update` | Required | Update multiple entries |
| POST | `/api/batch-parse` | Required | Parse batch selector input |

### **Dispatch Rules Endpoints**

| Method | Path | Authentication | Purpose |
|--------|------|----------------|---------|
| GET | `/api/dispatch-rules` | Required | Get all dispatch rules (JSON) |
| PUT | `/api/dispatch-rules/{name}` | Required | Update dispatch rule |
| POST | `/api/dispatch-rules/{name}/run` | Required | Trigger job immediately |

### **Job Status Endpoints**

| Method | Path | Authentication | Purpose |
|--------|------|----------------|---------|
| GET | `/api/jobs/recent` | Required | Get recent job executions (paginated) |
| GET | `/api/jobs/stats` | Required | Get job execution statistics |
| GET | `/api/jobs/{job_name}/stats` | Required | Get stats for specific job |

### **Form Actions (Traditional POST)**

| Method | Path | Form Fields | Purpose |
|--------|------|-------------|---------|
| POST | `/handle-action` | `action=mark_sent&date=YYYY-MM-DD` | Mark entry as sent |
| POST | `/handle-action` | `action=skip&date=YYYY-MM-DD` | Skip entry |
| POST | `/handle-action` | `action=move&from_date=...&to_date=...` | Move entry to new date |
| POST | `/handle-action` | `action=edit_selector&date=...&selector=...` | Update selector |
| POST | `/handle-action` | `action=edit_notes&date=...&notes=...` | Update notes |

---

## Job Scheduling & Execution

### **APScheduler Integration**

**Scheduler Type:** AsyncIOScheduler (non-blocking)

**Trigger Configuration:**
```python
CronTrigger(
    minute="*/10",          # Every 10 minutes
    timezone=sm.TAIWAN_TZ   # Taiwan time
)
```

**Job Setup:**
```python
scheduler.add_job(
    _run_dispatcher_trigger,
    trigger,
    id="dispatcher_trigger",
    name="Job Dispatcher (10min cycle)",
    max_instances=1,        # Prevent concurrent runs
    replace_existing=True
)
```

### **Job Dispatcher Algorithm**

```text
Current time in Taiwan TZ: 2026-05-30 06:15:00
Load dispatch rules from config/dispatch_rules.json
Load dispatcher state from state/dispatch_state.json

For each rule:
    ├─ Check if current time >= rule.time
    ├─ Check if current weekday in rule.weekdays
    ├─ Check if rule ran in current time window (rounded to 5 minutes)
    ├─ If all true AND rule hasn't run in window:
    │   ├─ Execute command(s) with env vars
    │   ├─ Update state with new run timestamp
    │   └─ Track execution in job history
    └─ Else: Skip rule
```

**Time Window Logic:**
- Prevents duplicate execution within 5-minute window
- Example: Rule runs at 06:00
  - First check at 06:02 → Execute
  - Second check at 06:04 → Skip (within window)
  - Check at 06:07 → Execute again (new window)

### **Execution with Retries**

```text
Attempt 1
    ↓
Exit code 0? → Mark success, finish
Exit code != 0? → Go to Attempt 2
    ↓
Wait 60 seconds
    ↓
Attempt 2
    ↓
Exit code 0? → Mark success, finish
Exit code != 0? → Go to Attempt 3
    ↓
Wait 60 seconds
    ↓
Attempt 3 (final)
    ↓
Exit code 0? → Mark success
Exit code != 0? → Mark failed, send error notification
```

**Timeout:** 60 seconds per attempt (total max: 3-4 minutes)

### **Environment Variable Isolation**

Jobs can have specific env vars via dispatch rules:

```json
{
  "name": "special-job",
  "time": "12:00",
  "days": [1, 3, 5],
  "commands": [["python", "special_task.py"]],
  "env": {
    "SPECIAL_MODE": "1",
    "SPECIAL_PARAM": "value"
  }
}
```

**Merge Strategy (Priority Order):**
```text
1. System environment variables (lowest priority)
    ↓
2. .env file variables (override system)
    ↓
3. Job-specific env vars from dispatch_rules.json (highest priority, override both)
    ↓
Pass merged environment to subprocess
```

Each layer overrides the previous one, so job-specific env vars take precedence over .env, which takes precedence over system env vars.

---

## Content Source Abstraction

### **Factory Pattern Flow**

```text
content_source_factory.get_active_source()
    ├─ Check CONTENT_SOURCE env var
    ├─ If "ezoe" → return EzoeContentSource()
    ├─ If "wix" → return WixContentSource()
    ├─ If "stmn1" → return StmnlContentSource()
    └─ Default: raise ValueError
```

### **EzoeContentSource Implementation**

**Selector Format:** `volume-lesson-day`
- Volume: 1-100 (scripture books)
- Lesson: 1-365 (days in reading plan)
- Day: 1-7 (day of week)

**Example:** `2-1-3` = Volume 2, Lesson 1, Wednesday

**Validation:**
```python
def validate_selector(selector: str) -> bool:
    match = re.fullmatch(r"(\d+)-(\d+)-(\d)", selector)
    if not match: return False
    vol, les, day = map(int, match.groups())
    return 1 <= vol <= 100 and 1 <= les <= 365 and 1 <= day <= 7
```

**Advancement:**
```python
def advance_selector(selector: str) -> str:
    vol, les, day = parse(selector)
    
    if day < 7:
        return f"{vol}-{les}-{day+1}"
    elif les < 365:
        return f"{vol}-{les+1}-1"
    elif vol < 100:
        return f"{vol+1}-1-1"
    else:
        # Wrap around
        return "1-1-1"
```

**Batch Parsing (with range syntax):**
```python
def parse_batch_selectors(input_text: str) -> List[str]:
    # Supports:
    # - "2-1-1 to 2-1-5" → ["2-1-1", "2-1-2", "2-1-3", "2-1-4", "2-1-5"]
    # - "2-1-1, 2-1-3, 2-1-5"
    # - "2-1-1\n2-1-2\n2-1-3"
    
    text = input_text.strip()
    
    # Check for range syntax
    if " to " in text:
        parts = text.split(" to ")
        start = parse_selector(parts[0].strip())
        end = parse_selector(parts[1].strip())
        return generate_range(start, end)
    
    # Split by comma or newline
    return [s.strip() for s in re.split(r'[,\n]+', text) if s.strip()]
```

### **WixContentSource Implementation**

**Selector Format:** Chinese weekday
- `【週一】`, `【週二】`, `【週三】`, `【週四】`, `【週五】`, `【週六】`, `【主日】`

**Note:** Does NOT support range syntax (no day-to-day progression)

**Validation:**
```python
def validate_selector(selector: str) -> bool:
    return selector in VALID_WEEKDAYS
```

**Batch UI Config:**
```python
def get_batch_ui_config() -> dict:
    return {
        "placeholder": "【週一】, 【週三】, 【週五】",
        "help_text": "Select one or more days of the week",
        "examples": ["【週一】", "【週三】"],
        "supports_range": False,
        "range_example": None
    }
```

---

## Testing Architecture

### **Test Coverage**

**Total Test Files:** ~25 test modules  
**Total Tests:** ~300+ test cases

**Test Categories:**

| Category | Files | Purpose |
|----------|-------|---------|
| **Unit Tests** | `test_schedule_manager.py`, `test_schedule_reply.py` | Test individual functions/classes |
| **Integration Tests** | `test_email_e2e.py`, `test_cron_job_integration.py` | Test component interactions |
| **Content Source Tests** | `test_content_sources.py`, `test_ezoe_validation.py` | Test content scraping |
| **API Tests** | `test_dashboard.py`, `test_authentication.py` | Test FastAPI endpoints |
| **Job Tests** | `test_job_dispatcher.py`, `test_cron_runner.py` | Test scheduling logic |
| **Security Tests** | `test_token_encryption.py`, `test_oauth_status.py` | Test encryption/auth |

### **Testing Strategy**

**Framework:** pytest with fixtures

**Key Fixtures (conftest.py):**
```python
@pytest.fixture
def temp_schedule(tmp_path):
    # Creates temporary schedule file for isolated testing

@pytest.fixture
def mock_gmail_service():
    # Mocks Gmail API to avoid network calls

@pytest.fixture
def sample_schedule_entries():
    # Provides pre-populated schedule for testing
```

**Mocking Strategy:**
```python
# Mock Gmail API
from unittest.mock import patch, MagicMock

@patch('oauth_utils.get_gmail_service')
def test_send_email(mock_gmail):
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service
    # Test email sending without hitting real Gmail
```

**Test Execution:**
```bash
pytest                          # Run all tests
pytest tests/test_schedule_manager.py  # Specific file
pytest -v                       # Verbose output
pytest --cov                    # Coverage report
pytest -k "test_advance_selector"  # Test by name pattern
```

---

## Configuration & Environment

### **Environment Variables (Comprehensive List)**

**Gmail API & Email Delivery:**
```bash
SMTP_USER=your-email@gmail.com
EMAIL_FROM=sender@example.com
EMAIL_TO=recipient1@example.com,recipient2@example.com
```

**Note:** OAuth2 credentials are stored in `token.json` and managed via the web dashboard OAuth flow, not via environment variables.

**Schedule & Selectors:**
```bash
SCHEDULE_FILE=state/ezoe_schedule.json
EZOE_SELECTOR=2-1-3                    # Set by daily runner
EZOE_VOLUME=2                          # Default volume for seed
EZOE_LESSON=1                          # Default lesson for seed
EZOE_DAY_START=1                       # Default day for seed
EZOE_SEND_WEEKDAY=                     # Override (e.g., "Mon", "週三")
EZOE_SEND_DATE=                        # Override (e.g., "2026-06-01")
RUN_FORCE=                             # Set to "1" to resend
```

**Admin Dashboard:**
```bash
ADMIN_DASHBOARD_USER=admin
ADMIN_DASHBOARD_PASSWORD=your-secure-password
SECRET_KEY=your-session-secret-key
```

**Admin Summaries & Replies:**
```bash
ADMIN_SUMMARY_TO=admin@example.com
ADMIN_SUMMARY_FROM=system@example.com
ADMIN_SUMMARY_SUBJECT_PREFIX=[DailyManna]
ADMIN_REPLY_FROM=admin@example.com
ADMIN_REPLY_CONFIRMATION_TO=admin@example.com
ADMIN_REPLY_SUBJECT_KEYWORD=Reply
```

**Content Source Selection:**
```bash
CONTENT_SOURCE=ezoe          # or "wix" or "stmn1"
```

**Job Dispatcher:**
```bash
DISPATCH_CONFIG=config/dispatch_rules.json
DISPATCH_STATE_FILE=state/dispatch_state.json
DISPATCH_DAILY_TIME=06:00
DISPATCH_SUMMARY_TIME=21:00
```

**Database:**
```bash
DATABASE_URL=sqlite:///./daily_manna.db
ENCRYPTION_KEY=base64-encoded-32-byte-key
```

**Logging & Debug:**
```bash
DEBUG=false
DEBUG_EMAIL=false                       # Saves raw HTML to state/
POLITE_DELAY_MS=1000                    # Delay between HTTP requests
```

### **Configuration Files**

#### **.env (Shell Environment)**
```bash
# Copy from .env.example before running
# Contains all runtime configuration
# Sourced by shell scripts before Python execution
```

#### **config/dispatch_rules.json**
```json
[
  {
    "name": "daily-send",
    "time": "06:00",
    "days": ["daily"],
    "commands": [["bash", "scripts/run_daily_stateful_ezoe.sh"]],
    "env": {}
  },
  {
    "name": "weekly-summary",
    "time": "21:00",
    "days": [6],
    "commands": [["bash", "scripts/run_weekly_schedule_summary.sh"]],
    "env": {}
  }
]
```

#### **pyproject.toml**
```toml
[project]
name = "daily-manna-email"
version = "1.0.0"
description = "Automated scripture lesson delivery system"
```

---

## Security Architecture

### **Authentication**

**Session-Based:**
- Uses Starlette SessionMiddleware
- Sessions stored in cookies with secret key signature
- HTTP-only flag prevents JavaScript access
- User credentials checked against env vars on login

**Code Location:** `app/security.py:require_user` dependency

### **Encryption at Rest**

**Email Encryption:**
- AES-256-GCM symmetric encryption
- Random IV generated per encryption
- Key: base64-decoded from `ENCRYPTION_KEY` env var
- Stored: Base64-encoded (ciphertext + IV) in database

**Code Location:** `app/email_encryption.py`

**OAuth Token Encryption:**
- Google Credentials serialized to JSON
- Encrypted with AES-256-GCM
- Key: same as above
- Stored in encrypted form in environment/state

**Code Location:** `app/token_encryption.py`

### **OAuth2 Integration**

**Gmail API Scope:**
- `gmail.send` - Send emails
- `gmail.readonly` - Read email metadata
- `gmail.modify` - Mark as read

**Flow:**
1. User initiates OAuth flow via dashboard
2. Redirected to Google consent screen
3. Authorization code returned
4. Exchanged for access + refresh tokens
5. Tokens encrypted and stored
6. Subsequent requests use cached/refreshed tokens

**Code Location:** `oauth_utils.py`, `app/main.py`

### **CSRF Protection**

**Method:**
- Session middleware provides CSRF tokens
- Forms include hidden CSRF field
- Starlette validates token on POST/PUT/DELETE

**Implementation:** Automatic via Starlette middleware

### **SQL Injection Protection**

**Method:**
- SQLAlchemy ORM parameterizes all queries
- No string formatting or concatenation
- Pydantic models validate input types

**Example:**
```python
# Safe (ORM parameterization)
session.query(Subscriber).filter(Subscriber.email_encrypted == encrypted_email)

# Never this (would be vulnerable)
session.execute(f"SELECT * FROM subscribers WHERE email='{email}'")
```

### **Rate Limiting**

**Polite Delay:**
```bash
POLITE_DELAY_MS=1000  # Delay between HTTP scraping requests
```

**APScheduler:**
- `max_instances=1` ensures single concurrent job
- 10-minute check interval prevents rapid firing

### **Input Validation**

**Pydantic Models:**
```python
class EntryPayload(BaseModel):
    date: dt.date              # Type checking
    selector: Optional[str]    # Optional with None default
    status: Optional[str]      # Normalized via field_validator
    
    @field_validator("status")
    def _normalize_status(cls, value):
        if value is None: return None
        return value.strip() or None
```

**Selector Validation:**
```python
# Each content source implements
def validate_selector(self, selector: str) -> bool:
    # Regex pattern matching
    # Range checking
    # Format verification
```

---

## Deployment Architecture

### **Deployment Options**

#### **Option 1: Traditional VPS with Cron**

```text
Server (Ubuntu 20.04+)
├── Python 3.9+ virtualenv
├── .env configuration file
├── state/ directory (persistent JSON)
├── SQLite database (or external PostgreSQL)
└── Cron jobs:
    - Every 10 minutes: python job_dispatcher.py
    - Or: uvicorn app.main:app (for web dashboard)
```

**Cron Entry:**
```bash
# Run dispatcher every 10 minutes
*/10 * * * * cd /app && python job_dispatcher.py

# Or use Systemd timer if preferred
```

#### **Option 2: PythonAnywhere**

See `docs/DEPLOYMENT_PYTHONANYWHERE.md` for detailed walkthrough.

**Key Steps:**
1. Upload code to PythonAnywhere
2. Create virtualenv with dependencies
3. Configure web app using ASGI (uvicorn)
4. Set up scheduled tasks (replaces cron)
5. Configure `.env` in application directory

#### **Option 3: Docker Container**

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

# Can run either dispatcher or web server
CMD ["python", "job_dispatcher.py"]
# OR
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose:**
```yaml
version: '3.8'
services:
  dispatcher:
    build: .
    environment:
      - CONTENT_SOURCE=ezoe
      - DATABASE_URL=postgresql://...
    volumes:
      - ./state:/app/state
    command: python job_dispatcher.py
  
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
    command: uvicorn app.main:app --host 0.0.0.0
```


### **Database Migration**

**SQLite to PostgreSQL:**

```bash
# 1. Export from SQLite
sqlite3 daily_manna.db ".dump subscribers" > subscribers_dump.sql

# 2. Import to PostgreSQL
psql -U postgres -d daily_manna < subscribers_dump.sql

# 3. Update DATABASE_URL env var
export DATABASE_URL="postgresql://user:pass@host:5432/daily_manna"

# 4. Restart application
```

### **Backup Strategy**

**What to Backup:**

| Path | Content | Frequency |
|------|---------|-----------|
| `state/ezoe_schedule.json` | **CRITICAL** - schedule state | Every hour |
| `state/job_history.json` | Job execution history | Every day |
| Database (SQLite or PostgreSQL) | **CRITICAL** - subscriber data | Every hour |
| `.env` | **SECRET** - credentials | Manual (keep encrypted) |

**Backup Script:**
```bash
#!/bin/bash
BACKUP_DIR="/backups/daily-manna"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup schedule
cp state/ezoe_schedule.json "$BACKUP_DIR/schedule_$TIMESTAMP.json"

# Backup database
if [ -f "daily_manna.db" ]; then
  sqlite3 daily_manna.db ".backup '$BACKUP_DIR/db_$TIMESTAMP.db'"
else
  pg_dump $DATABASE_URL > "$BACKUP_DIR/db_$TIMESTAMP.sql"
fi

# Keep only last 30 days
find "$BACKUP_DIR" -mtime +30 -delete
```

---

## Code Metrics & Statistics

### **Codebase Size**

| Component | Files | Lines of Code | Purpose |
|-----------|-------|-------------|---------|
| **Root modules** | 14 | ~4,700 | Core business logic |
| **FastAPI app** | 12 | ~3,300 | Web application |
| **Bash scripts** | 5 | ~200 | Cron wrappers |
| **Tests** | ~25 | ~2,000+ | Test coverage |
| **Configuration** | 5 | ~100 | Config files |
| **Total (excluding tests)** | ~36 | ~8,300 | Production code |

### **Module Complexity**

**Cyclomatic Complexity (estimated):**

| Module | Complexity | Notes |
|--------|-----------|-------|
| `sjzl_daily_email.py` | High | Multiple code paths for content wrapping |
| `schedule_manager.py` | Medium | Schedule logic + timezone handling |
| `app/main.py` | High | Many routes and form handlers |
| `schedule_reply_processor.py` | High | Many instruction types to process |
| `job_dispatcher.py` | Medium | Time evaluation and rule matching |

### **Code Quality**

**Testing Coverage (estimated):**
- Core business logic: 85%+
- API endpoints: 75%+
- Error paths: 60%+
- Integration paths: 70%+

**Linting:**
- Uses standard Python conventions (PEP 8)
- Type hints in most modules (Python 3.9+)
- Docstrings on public functions

---

## Design Patterns Identified

### **1. Factory Pattern** (content sources)
- Abstract interface: `ContentSource`
- Concrete implementations: `EzoeContentSource`, `WixContentSource`
- Factory function: `content_source_factory.get_active_source()`

### **2. State Machine Pattern** (schedule entries)
- States: pending → sent, or pending → skipped
- Transitions: based on admin actions (via dashboard or reply processor) or automatic processing
- Side effects: timestamp updates on sent, reply token consumption

### **3. Observer/Listener Pattern** (reply processing)
- Observable: Gmail inbox (polled)
- Observer: `schedule_reply_fetcher`
- Event handlers: instruction processors

### **4. Dependency Injection** (FastAPI)
- Dependencies: `require_user`, `get_config`
- Injected into: route handlers
- Benefits: testability, loose coupling

### **5. Singleton Pattern** (global state)
- `AppConfig` - Configuration singleton
- `CronJobRunner` - Scheduler singleton
- `JobTracker` - History tracker singleton

### **6. Template Method Pattern** (email rendering)
- Abstract steps: fetch, parse, wrap, send
- Customized in: `sjzl_daily_email`
- Varied by: content source implementation

### **7. Strategy Pattern** (selector handling)
- Context: `ScheduleEntry`
- Strategies: `EzoeContentSource.advance_selector()`, `WixContentSource.advance_selector()`
- Selection: via `content_source_factory`

### **8. Repository Pattern** (schedule persistence)
- Entity: `ScheduleEntry`
- Repository: `Schedule` class (load/save from JSON)
- Query methods: `get_entry()`, `get_pending_entries()`

### **9. Decorator Pattern** (Pydantic validators)
```python
@field_validator("status")
def _normalize_status(cls, value):
    # Cross-cutting concern: input normalization
    return value.strip() if value else None
```

### **10. Builder Pattern** (email composition)
```python
message = MIMEMultipart("alternative")
message.attach(MIMEText(body_text, "plain", "utf-8"))
message.attach(MIMEText(body_html, "html", "utf-8"))
# Fluent construction of complex object
```

---

---

## Dependencies & Technology Stack

### **Core Framework**

| Package | Version | Purpose |
|---------|---------|---------|
| **FastAPI** | 0.124+ | Web framework |
| **Starlette** | 0.50+ | ASGI server foundation |
| **Uvicorn** | 0.38+ | ASGI application server |
| **Pydantic** | 2.12+ | Data validation |

### **Scheduling & Jobs**

| Package | Version | Purpose |
|---------|---------|---------|
| **APScheduler** | 3.10+ | Background job scheduling |
| **schedule** | 1.2+ | Alternative scheduler (used in some modules) |

### **Database & ORM**

| Package | Version | Purpose |
|---------|---------|---------|
| **SQLAlchemy** | 1.4+ | ORM layer |
| **psycopg2cffi** | 2.9+ | PostgreSQL driver |

### **Gmail & Email**

| Package | Version | Purpose |
|---------|---------|---------|
| **google-auth** | 2.41+ | Google authentication |
| **google-auth-oauthlib** | 1.2+ | OAuth 2.0 support |
| **google-api-python-client** | 2.154+ | Gmail API client |

### **Web Scraping & Parsing**

| Package | Version | Purpose |
|---------|---------|---------|
| **requests** | 2.32+ | HTTP client |
| **BeautifulSoup4** | 4.14+ | HTML parsing |
| **soupsieve** | 2.8+ | CSS selector library |

### **Templating & Frontend**

| Package | Version | Purpose |
|---------|---------|---------|
| **Jinja2** | 3.1+ | Template engine |
| **MarkupSafe** | 3.0+ | Safe template rendering |

### **Security**

| Package | Version | Purpose |
|---------|---------|---------|
| **cryptography** | 43.0+ | Encryption (AES, etc.) |

### **Utilities**

| Package | Version | Purpose |
|---------|---------|---------|
| **pyasn1** | 0.6+ | ASN.1 support |
| **typing-extensions** | 4.15+ | Type hints backport |
| **opencc-python-reimplemented** | 0.1+ | Chinese character conversion |

### **Testing**

| Package | Version | Purpose |
|---------|---------|---------|
| **pytest** | (via requirements-test.txt) | Test framework |
| **pytest-cov** | 5.0+ | Coverage reporting |

---

## Future Extensibility & Scalability

### **Extension Points**

#### **1. Add New Content Source**

```python
# Create new class
class MyContentSource(ContentSource):
    def get_daily_content(self, selector: str) -> ContentBlock:
        # Implement fetching logic
        pass
    
    def get_selector_type(self) -> str:
        return "my-custom-type"
    
    # ... implement other abstract methods

# Register in factory
def get_active_source() -> ContentSource:
    source = os.getenv("CONTENT_SOURCE", "ezoe").lower()
    
    if source == "my-source":
        return MyContentSource()
    # ... other sources
```

#### **2. Add Custom Job Type**

```python
# 1. Add new dispatch rule to config/dispatch_rules.json
{
  "name": "custom-job",
  "time": "14:00",
  "days": [1, 3, 5],
  "commands": [["python", "my_custom_job.py"]]
}

# 2. Implement my_custom_job.py
# 3. System will auto-discover and execute via dispatcher
```

#### **3. Add New Admin Reply Command**

```python
# In schedule_reply.py:parse_reply_body()
instructions = [
    ...
    Instruction(type="my_command", entry_date=date, args={"param": value})
]

# In schedule_reply_processor.py:apply_instructions()
elif instr.type == "my_command":
    # Implement custom logic
    schedule.entries[date].custom_field = instr.args["param"]
```

### **Scalability Limitations**

**Current Design Assumes:**
1. Single machine (no distributed locking)
2. JSON file doesn't grow excessively (1 entry/day)
3. Single dispatcher process
4. Email sending doesn't need sharding

**For 100x Growth:**

| Limitation | Solution |
|-----------|----------|
| JSON file becomes slow | Migrate to database (PostgreSQL) |
| Single dispatcher bottleneck | Add distributed locking (Redis) |
| Email throughput limited | Implement job queue (Celery) |
| No redundancy | Add load balancer + multiple instances |
| No audit trail | Add event sourcing or audit table |

### **Database Migration Path**

```text
Phase 1: Keep JSON, migrate to database for subscribers
├─ SQLAlchemy ORM for Subscriber model
└─ Encryption at rest for emails

Phase 2: Migrate schedule to database
├─ Table: schedule_entries (date, selector, status, notes)
├─ Replace JSON load/save with ORM queries
└─ Add indexes for fast lookups

Phase 3: Add job queue
├─ Celery or RQ for async job processing
├─ Redis backend for state
└─ Horizontal scaling of job workers

Phase 4: Distributed system
├─ Multiple dispatcher instances
├─ Distributed locking (Redis)
├─ Message broker for job coordination
└─ Monitoring/metrics (Prometheus)
```

### **Performance Optimization Opportunities**

1. **Caching Layer** - Redis cache for schedule, content
2. **Database Indexes** - On date, status, content_source
3. **Async I/O** - Make requests non-blocking in scraper
4. **Batch Operations** - Email multiple recipients in single API call
5. **Content CDN** - Cache scraped HTML in CDN
6. **Lazy Loading** - Load schedule only when needed

---

## Summary

The **Daily Manna Email** system is a well-architected automation platform that demonstrates:

✅ **Strong separation of concerns** - Clear module boundaries  
✅ **Extensibility** - Factory pattern for content sources  
✅ **Reliability** - Stateful tracking, retry logic, monitoring  
✅ **Security** - OAuth2, encryption at rest, input validation  
✅ **Simplicity** - JSON persistence, CLI-friendly  
✅ **Testability** - Comprehensive test suite, mocking support  

**Core Strengths:**
- Clean abstraction layer for multiple content sources
- Flexible job dispatch (works with cron or containers)
- Simple yet effective admin workflow (email-based replies)
- Complete audit trail via job history

**Areas for Future Enhancement:**
- Migrate to database for scalability
- Add distributed job queue for throughput
- Implement metrics/monitoring dashboard
- Add multi-language support

---

**Document Generated:** May 30, 2026  
**Total Analysis Time:** Comprehensive codebase review  
**Last Update:** Current commit (`feature/email-activity-dashboard`)

