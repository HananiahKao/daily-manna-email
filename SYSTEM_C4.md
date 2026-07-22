# Daily Manna Email — C4 Model

## Level 1 · System Context

- **Person · Daily Recipient** — receives the daily "聖經之旅" email content; no direct interaction other than reading messages.
- **Person · Admin Maintainer** — reviews weekly summaries, sends adjustment replies, and oversees delivery.
- **Person · Web Admin** — accesses the web dashboard to interactively manage schedule entries, view calendar, and perform administrative tasks.
- **System · Daily Manna Email** — automates lesson selection, email delivery, scheduling, admin feedback processing, and provides a web dashboard for management.
- **System · EZOe Content Source (ezoe.work)** — provides lesson HTML scraped for selector-based sends.
- **System · Legacy Content Source (four.soqimp.com)** — fallback lesson discovery endpoint for SJZL mode.
- **System · Gmail API** — OAuth-authenticated service for sending emails and reading admin replies.

```mermaid
flowchart LR
    Admin([Admin Maintainer])
    WebAdmin([Web Admin])
    Recipient([Daily Recipient])
    System[[Daily Manna Email]]
    Gmail[(Gmail API)]
    Ezoe[(EZOe Content Source)]
    Legacy[(Legacy Content Source)]

    Admin <-- Weekly summary & replies --> System
    WebAdmin <-- Interactive management --> System
    System --> Recipient
    System --> Gmail
    Gmail --> Recipient
    Admin --> Gmail -. replies .-> System
    System <---> Ezoe
    System <---> Legacy
```

```
[Admin Maintainer] ⇄ [Daily Manna Email] ⇄ Gmail API
             ↑                          ⇣
       (Weekly summary & replies)   [Daily Recipient]

[Web Admin] ⇄ [Daily Manna Email]

[Daily Manna Email] ⇄ [EZOe Content Source]
[Daily Manna Email] ⇄ [Legacy Content Source]
```

## Level 2 · Containers

| Container | Tech | Responsibilities | Key Interactions |
|-----------|------|------------------|------------------|
| **Cron / Scheduler** | Bash (`scripts/run_*`) | Entry points triggered by cron; loads `.env`; invokes Python CLIs. | Calls Python containers below. |
| **Cron Job Runner** | Python (APScheduler, `app/cron_runner.py`) | Background job scheduler using APScheduler; manages job execution, retries, and parallel processing. | Integrates with Job Dispatcher and Job Tracker; invokes scheduled jobs. |
| **Job Dispatcher** | Python (`job_dispatcher.py`) | Determines which jobs should run based on schedule rules; manages job execution state. | Reads dispatch rules from config; interacts with Cron Job Runner. |
| **Job Tracker** | Python (`app/job_tracker.py`) | Tracks job executions, history, and statistics; provides pagination and status monitoring. | Stores execution history in `state/job_history.json`; used by dashboard. |
| **Schedule Service** | Python (`schedule_tasks.py`, `schedule_manager.py`) | Maintains `state/ezoe_schedule.json`; calculates next selector; renders weekly summaries; issues reply tokens. | Reads/writes JSON state; invokes Email Delivery and Web Dashboard. |
| **Email Delivery** | Python (`sjzl_daily_email.py`) | Fetches lesson HTML, wraps content, composes multipart emails, sends via Gmail API. | Reads env vars; calls `requests` for scraping; uses Gmail API. |
| **Content Scraper** | Python (`ezoe_week_scraper.py`) | Pulls specific lesson/day HTML from ezoe.work with UTF-8 safeguards. | Invoked by Email Delivery when `EZOE_SELECTOR` is set. |
| **Admin Reply Processor** | Python (`schedule_reply.py`, `schedule_reply_processor.py`, `schedule_reply_fetcher.py`, `scripts/process_schedule_replies.py`) | Fetches Gmail API mail, parses reply tokens, applies adjustments, sends confirmation emails, archives results. | Uses Gmail API; updates schedule; calls Email Delivery. |
| **Web Dashboard** | Python (FastAPI, `app/main.py`, `app/templates`, `app/static`) | Provides interactive web interface for viewing and editing schedule entries, calendar display, job status monitoring, and administrative actions. | Reads/writes JSON state via Schedule Service; interacts with Job Tracker for job monitoring. |
| **State Store** | JSON files (`state/*.json`) | Persists schedule, weekly summary, reply processing outcomes, HTML archives, and job execution history. | Used by Schedule Service, Admin Reply Processor, Job Tracker, and Web Dashboard. |

Data flow: Cron scripts orchestrate the Schedule Service, which selects a selector, triggers the Email Delivery container (which in turn uses the Content Scraper when needed) and updates the State Store. Admin Reply Processor reads weekly emails, applies modifications to the State Store, and sends confirmations through Email Delivery. Web Dashboard provides interactive access to Schedule Service and State Store for manual management.

```mermaid
flowchart TB
    subgraph Cron["Cron / Scheduler (scripts/run_*)"]
        DirectCron[[Direct Script Execution]]
    end

    subgraph CronRunner["Cron Job Runner (app/cron_runner.py)"]
        APScheduler[[APScheduler Background]]
        RetryLogic[[Retry Management]]
        ParallelExec[[Parallel Execution]]
    end

    subgraph JobDispatcher["Job Dispatcher (job_dispatcher.py)"]
        DispatchRules[[Dispatch Rules]]
        StateMgmt[[State Management]]
        JobSelection[[Job Selection]]
    end

    subgraph JobTracker["Job Tracker (app/job_tracker.py)"]
        ExecutionHistory[[Execution History]]
        Statistics[[Job Statistics]]
        Pagination[[Pagination]]
    end

    subgraph Schedule["Schedule Service (schedule_tasks.py / schedule_manager.py)"]
        NextEntry[[next-entry]]
        EnsureWeek[[ensure-week]]
        MarkSent[[mark-sent]]
    end

    subgraph Email["Email Delivery (sjzl_daily_email.py)"]
        FetchCompose[[Fetch & Compose]]
        GmailClient[[send_email]]
    end

    subgraph Scraper["Content Scraper (ezoe_week_scraper.py)"]
        DayHtml[[get_day_html]]
    end

    subgraph Admin["Admin Reply Processor"]
        FetchGmail[[process_schedule_replies.py]]
        ParseTokens[[schedule_reply.py]]
        ApplyInstr[[schedule_reply_processor.py]]
    end

    subgraph WebDash["Web Dashboard (app/main.py)"]
        DashboardAPI[[Dashboard & APIs]]
        Authenticate[[Authentication]]
        JobMonitoring[[Job Status Monitoring]]
    end

    State[(state/*.json & HTML archives)]
    GmailMailbox[(Gmail API)]
    Ezoe[(ezoe.work)]
    Legacy[(four.soqimp.com)]

    %% Direct cron path (scripts/run_*)
    DirectCron --> NextEntry
    DirectCron --> EnsureWeek
    DirectCron --> FetchGmail

    %% APScheduler path
    APScheduler --> DispatchRules
    DispatchRules --> JobSelection
    JobSelection --> ParallelExec
    ParallelExec --> NextEntry
    ParallelExec --> EnsureWeek
    ParallelExec --> FetchGmail

    NextEntry --> FetchCompose
    FetchCompose --> DayHtml
    DayHtml --> FetchCompose
    FetchCompose --> GmailClient
    GmailClient --> GmailMailbox
    EnsureWeek --> GmailClient
    FetchGmail --> GmailMailbox
    FetchGmail --> ParseTokens
    ParseTokens --> ApplyInstr
    ApplyInstr --> State
    NextEntry --> State
    EnsureWeek --> State
    MarkSent --> State
    FetchCompose --> State
    ApplyInstr --> GmailClient
    FetchCompose --> Ezoe
    FetchCompose --> Legacy

    %% Job tracking
    ParallelExec --> ExecutionHistory

    ExecutionHistory --> Statistics
    Statistics --> Pagination
    Pagination --> DashboardAPI

    DashboardAPI --> State
    Authenticate --> DashboardAPI
    DashboardAPI --> NextEntry
    DashboardAPI --> EnsureWeek
    DashboardAPI --> JobMonitoring
    JobMonitoring --> Statistics
```

## Level 3 · Components (Schedule Service, Admin Loop & Web Dashboard)

### Schedule Service Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `schedule_manager.Schedule` | Core model for entries; handles persistence, timezone logic, and lookups. | Stores data in `state/ezoe_schedule.json` (override via `SCHEDULE_FILE`). |
| `schedule_tasks.next-entry` | CLI to compute the next selector/date pair, honoring overrides (`EZOE_SEND_WEEKDAY`, `EZOE_SEND_DATE`). | Exported selector feeds the daily runner. |
| `schedule_tasks.ensure-week` | Pre-populates upcoming week, issues reply tokens, renders HTML & text summaries. | Sends admin email via `sjzl_daily_email.send_email` when `--email`. |
| `schedule_tasks.mark-sent` | Updates entry status to `sent` with timestamp after successful delivery. | Called by `run_daily_stateful_ezoe.sh`. |

### Email Delivery Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `sjzl_daily_email.get_day_html` (via `ezoe_week_scraper`) | Retrieves HTML for a given selector; adds `<h3>` headings; strips chrome. | Ensures UTF-8 decoding and polite delays. |
| `sjzl_daily_email._wrap_email_html_with_css` | Scopes inline and linked CSS for safe email rendering. | Combines content with `<meta charset='utf-8'>`. |
| `sjzl_daily_email.send_email` | Sends multipart/alternative emails via Gmail API (`SMTP_USER`, `EMAIL_FROM`, etc.). | Reused by weekly summaries and reply confirmations. |

### Admin Reply Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `schedule_reply.issue_reply_tokens` | Generates expiring tokens stored in schedule metadata. | Adds `meta.reply_tokens` entries with TTL. |
| `schedule_reply.parse_reply_body` | Parses admin email commands (`[TOKEN] verb args…`). | Supports verbs: `keep`, `skip`, `move`, `selector`, `status`, `note`, `override`. |
| `schedule_reply_processor.apply_instructions` | Applies parsed commands to schedule entries, tracking outcome. | Removes tokens on success; flags errors for confirmation email. |
| `schedule_reply_fetcher.process_mailbox` | Uses Gmail API, filters allowed senders, extracts text, invokes processor, archives results. | Uses `ADMIN_REPLY_*` env vars. |
| `scripts/process_schedule_replies.py` | CLI wrapper with `--limit` and `--dry-run` for cron/tests. | Used by `scripts/run_schedule_reply_processor.sh`. |

### Cron Job Runner Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `CronJobRunner` | Main scheduler class using APScheduler for background job management. | Manages job execution, retries, and parallel processing. |
| `_setup_jobs` | Configures scheduled jobs using cron triggers. | Sets up 10-minute dispatcher trigger. |
| `_run_dispatcher_trigger` | Executes job dispatcher system to determine which jobs to run. | Coordinates job selection and parallel execution. |
| `_execute_job_from_rule` | Executes a specific job from a dispatcher rule. | Handles job-specific environment variables and tracking. |
| `_execute_job_with_retries` | Executes a job with retry logic. | Handles up to 3 retries with 1-minute delay. |
| `_execute_job_single_attempt` | Executes a single job attempt without retries. | Tracks execution, logs output, and handles timeouts. |
| `get_cron_runner` / `shutdown_cron_runner` | Global instance management functions. | Singleton pattern for scheduler lifecycle. |

### Job Dispatcher Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `DispatchRule` | Data class representing a single job rule with schedule and commands. | Contains time, weekdays, commands, and environment variables. |
| `load_rules` | Loads dispatch rules from JSON configuration file or defaults. | Handles fallback to default rules if config file is missing. |
| `get_jobs_to_run` | Determines which jobs should run based on current time and state. | Checks schedule, last run time, and max delay constraints. |
| `update_job_run_time` | Updates the last run time for a job in the dispatch state. | Tracks job execution times in `state/dispatch_state.json`. |
| `load_state` / `save_state` | Persistence functions for dispatch state. | Handles reading/writing to state file. |

### Job Tracker Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `JobExecutionResult` | Data class representing the result of a job execution. | Tracks status, logs, duration, exit code, and metadata. |
| `JobTracker` | Main tracker class for managing job execution history. | Stores history in `state/job_history.json`. |
| `start_job` | Starts tracking a new job execution. | Creates a new JobExecutionResult instance. |
| `update_job` | Updates job execution details. | Tracks status changes, logs, errors, and metadata. |
| `retry_job` | Marks a job for retry if retries are available. | Handles retry counting and status reset. |
| `get_recent_executions` | Returns recent job executions with pagination. | Supports filtering by job name and pagination. |
| `get_job_stats` | Returns statistics for job executions. | Provides success rate, average duration, and status counts. |
| `get_job_tracker` | Global instance management function. | Singleton pattern for tracker lifecycle. |

### Web Dashboard Components

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `app.main.create_app` | Bootstraps FastAPI app with mounted static files, Jinja2 templates, and routes. | Imports schedule modules; configures authentication middleware. |
| `app.main.dashboard` | Renders calendar dashboard HTML; loads week data via Schedule. | Requires authentication; displays start/end week, messages/errors. |
| `app.main.api_month` | JSON API for monthly calendar grid with entry serialization. | Fetches schedule entries; includes calendar grid padding. |
| API endpoints (`api_upsert_entry`, `api_move_entry`, `api_move_entries`) | Handles CRUD operations on schedule entries via JSON payloads. | Validates payloads; persists to JSON state. |
| `app.main.handle_action` | Processes form-based actions (mark sent, skip, note, move, etc.). | Accepts form data; redirects with messages/errors. |
| `app.security.require_user` | Dependency for authentication; checks credentials. | Uses `USERNAME`/`PASSWORD` env vars or default. |

```mermaid
flowchart LR
    subgraph CronRunnerSvc["Cron Job Runner"]
        CronRunner[[CronJobRunner]]
        SetupJobs[[_setup_jobs]]
        RunDispatcher[[_run_dispatcher_trigger]]
        ExecuteFromRule[[_execute_job_from_rule]]
        ExecuteWithRetries[[_execute_job_with_retries]]
        ExecuteSingleAttempt[[_execute_job_single_attempt]]
        GetRunner[[get_cron_runner]]
        ShutdownRunner[[shutdown_cron_runner]]
    end

    subgraph JobDispatcherSvc["Job Dispatcher"]
        DispatchRule[[DispatchRule]]
        LoadRules[[load_rules]]
        GetJobsToRun[[get_jobs_to_run]]
        UpdateJobRunTime[[update_job_run_time]]
        LoadState[[load_state]]
        SaveState[[save_state]]
    end

    subgraph JobTrackerSvc["Job Tracker"]
        JobResult[[JobExecutionResult]]
        JobTracker[[JobTracker]]
        StartJob[[start_job]]
        UpdateJob[[update_job]]
        RetryJob[[retry_job]]
        GetRecentExecutions[[get_recent_executions]]
        GetJobStats[[get_job_stats]]
        GetJobTracker[[get_job_tracker]]
    end

    subgraph ScheduleSvc["Schedule Service"]
        Manager[[schedule_manager.Schedule]]
        NextEntry[[schedule_tasks.next-entry]]
        EnsureWeek[[schedule_tasks.ensure-week]]
        MarkSent[[schedule_tasks.mark-sent]]
    end

    subgraph EmailSvc["Email Delivery"]
        DayHtml[[sjzl_daily_email.get_day_html]]
        WrapHtml[[sjzl_daily_email._wrap_email_html_with_css]]
        SendEmail[[sjzl_daily_email.send_email]]
    end

    subgraph AdminSvc["Admin Reply Pipeline"]
        IssueTokens[[schedule_reply.issue_reply_tokens]]
        ParseBody[[schedule_reply.parse_reply_body]]
        ApplyInstr[[schedule_reply_processor.apply_instructions]]
        FetchMailbox[[schedule_reply_fetcher.process_mailbox]]
    end

    subgraph WebSvc["Web Dashboard"]
        CreateApp[[app.main.create_app]]
        Dashboard[[app.main.dashboard]]
        ApiMonth[[app.main.api_month]]
        ApiCrud[[API Endpoints]]
        HandleAction[[app.main.handle_action]]
        AuthDep[[app.security.require_user]]
        JobMonitoring[[Job Status Monitoring]]
    end

    State[(state/*.json & HTML archives)]

    CronRunner --> SetupJobs
    SetupJobs --> RunDispatcher
    RunDispatcher --> GetJobsToRun
    GetJobsToRun --> ExecuteFromRule
    ExecuteFromRule --> ExecuteWithRetries
    ExecuteWithRetries --> ExecuteSingleAttempt
    ExecuteSingleAttempt --> StartJob
    ExecuteSingleAttempt --> UpdateJob
    ExecuteSingleAttempt --> NextEntry
    ExecuteSingleAttempt --> EnsureWeek
    ExecuteSingleAttempt --> FetchMailbox

    NextEntry --> Manager
    EnsureWeek --> IssueTokens
    EnsureWeek --> SendEmail
    MarkSent --> Manager
    DayHtml --> WrapHtml --> SendEmail
    FetchMailbox --> ParseBody --> ApplyInstr --> Manager
    ApplyInstr --> SendEmail

    Dashboard --> Manager
    ApiMonth --> Manager
    ApiCrud --> Manager
    HandleAction --> Manager
    AuthDep --> Dashboard
    AuthDep --> ApiMonth
    AuthDep --> ApiCrud
    AuthDep --> HandleAction
    Manager --> State
    IssueTokens --> Manager
    FetchMailbox --> IssueTokens

    JobMonitoring --> GetRecentExecutions
    JobMonitoring --> GetJobStats
    GetRecentExecutions --> JobResult
    GetJobStats --> JobTracker
    JobTracker --> StartJob
    JobTracker --> UpdateJob
    JobTracker --> RetryJob
    JobTracker --> GetRecentExecutions
    JobTracker --> GetJobStats
    JobResult --> State
```

## Deployment & Infrastructure Notes

- **Environment Configuration** — `.env` holds Gmail API, dashboard credentials (`USERNAME`, `PASSWORD`), and schedule overrides; scripts source it automatically. Key vars: `EZOE_SELECTOR`, `SMTP_*`, `EMAIL_*`, `ADMIN_SUMMARY_*`, `RUN_FORCE`, `EZOE_VOLUME/EZOE_LESSON/EZOE_DAY_START`.
- **State Management** — JSON files and HTML archives under `state/` act as lightweight persistence. Ensure cron jobs and web server have read/write access.
- **External Dependencies** — Outbound HTTPS (scraping) and Gmail API connectivity must be available. Rate limiting is enforced via `POLITE_DELAY_MS`.
- **Web Deployment** — FastAPI app can be run via `uvicorn` or ASGI server; mounted static files and Jinja2 templates for frontend assets.

This textual C4 description complements `SYSTEM_ARCHITECTURE.md` by emphasizing structural boundaries and interactions across system levels.
