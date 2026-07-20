# Daily Manna Email System: Comprehensive Improvement Plan (2026)

**Planning Period:** June 2026 – September 2026 (4 months)  
**Planner:** Claude Code + Hananiah Kao  
**Last Updated:** June 29, 2026

---

## 📋 Quick Status Checklist

### Phase 1: Delivery Reliability (June) — P=1, S=1
- [x] **1.1.1** Commit 1: Capture Gmail message IDs ✅ DONE
- [x] **1.1.2** Commit 2: Store message IDs with delivery tracking ✅ DONE
- [x] **1.1.3** Commit 3: Add Gmail recovery logic on startup ✅ DONE
- [x] **1.1.4** Commit 4: Integration test for recovery ✅ DONE
- [x] **1.2** Remove email addresses from logs (privacy fix) ✅ DONE
- [x] **1.3** Add JSON schema validation for dispatch rules ✅ DONE

**Phase 1 Progress:** 6/6 tasks complete (100%) ✅ COMPLETE

### Phase 2: Subscriber Database Integration (July) — P=1, S=2
- [x] **2.1** Migrate from EMAIL_TO env var to database ✅
- [x] **2.2** Add subscriber management API endpoints ✅
- [x] **2.3** Subscriber onboarding flow ✅
- [x] **2.4** (Bonus) Instant test send button in dashboard ✅
- [x] **2.5** Add display names to content sources (Polish) ✅
  - Auto-disambiguates when multiple sources share same display name
  - Signup shows Chinese titles; admin dashboard shows technical names
- [x] **2.6** Disable EZOE content source (Polish) ✅
- [x] **2.7** Refactor send_email() to require recipients parameter (Polish) ✅
- [x] **2.8** Admin dashboard indicators for disabled sources (Polish) ✅
- [x] **2.9** Make test sends completely side-effect-free (Polish) ✅

**Phase 2 Progress:** 4/4 core + 5/5 polish complete (100%) ✅ COMPLETE

### Phase 3: Dashboard & Observability (August) — P=2, S=2
- [x] **3.0** Extract error messages from job logs ✅ DONE (Phase 3.0)
- [x] **3.1** Enhance job history dashboard ✅ DONE (Phase 3.1)
- [x] **3.2** Email delivery status page (user-facing) ✅ DONE (Phase 3.2)
- [ ] **3.3** Real-time dashboard updates with AJAX
- [ ] **3.4** Dashboard UX improvements
- [x] **3.2.1** Add missing unsubscribe page ✅ DONE (Bugfix)

**Phase 3 Progress:** 4/6 tasks complete (67%)

### Phase 4: Email Formatting & Polish (September) — P=2–3, S=2–3
- [ ] **4.0** Full mobile support for dashboard
- [ ] **4.1** Fix persistent messages in dashboard UI
- [ ] **4.2** Email HTML/CSS improvements
- [ ] **4.3** Expand content sources (channel management)
- [ ] **4.4** Documentation & architecture guide
- [ ] **4.5** Deployment & scaling preparation

**Phase 4 Progress:** 0/6 tasks complete (0%)

### Phase 5: Testing Infrastructure (Post-September)
- Local production orchestrator (Docker Compose simulation of Render)
- End-to-end test scenarios (crash recovery, backfilling, multi-send)
- Separate project: `/Users/hananiah/Developer/daily-manna-testing/`

---

**Overall Progress:** 22/28 tasks complete (79%) | Phase 2 ✅ COMPLETE | Phase 3 (67%) | Pre-Phase-4 Privacy ⏳

---

## Executive Summary

This plan consolidates all improvement work for the Daily Manna Email system, organizing tasks by:
- **P (Priority):** 1 (critical) → 3 (low)
- **S (Severity):** 1 (blocking) → 3 (cosmetic)

Tasks are distributed across 4 months before senior high school starts, with focus on:
1. **Phase 1 (June):** Delivery reliability (critical blocking issues)
2. **Phase 2 (July):** Subscriber DB integration (enables production use)
3. **Phase 3 (August):** Dashboard & observability (admin DX)
4. **Phase 4 (September):** Polish & future architecture (low-priority enhancements)

---

## Phase 1: Critical Delivery Reliability (June 2026)

**Goal:** Eliminate duplicate emails and ensure system resilience.  
**P/S Ratings:** P=1, S=1 (must complete before production use)

### Task 1.1: Per-Recipient Delivery Tracking with Gmail Recovery ✅ IN PROGRESS
**Status:** Commit 1 ✅ done; Commits 2-4 pending  
**P/S:** P=1, S=1  

**Commit 1** ✅ **DONE**: Capture Gmail Message IDs
- Modified `send_email()` to return `{recipient: message_id}` dict
- All 341 tests pass
- **Git:** `0c3deef ✨ feat(send): capture Gmail message IDs`

**Commit 2** ✅ **DONE**: Store Message IDs with Idempotent Tracking
- New module `delivery_tracker.py` manages per-recipient delivery records
- Stores message IDs and timestamps in `state/deliveries.json` (separate from schedule)
- Filters recipients before sending: skips if already delivered today
- Records deliveries immediately after successful send (idempotent)
- Enables crash recovery: restarting won't duplicate emails
- 358 tests pass; includes 3 new integration tests for recovery scenarios
- **Git:** `17e7ff7 ✨ feat(send): idempotent delivery tracking`

**Commit 3** ✅ **DONE**: Add Gmail Recovery Logic on Startup
- New module `gmail_recovery.py` queries Gmail sent folder to backfill missing records
- On startup, for each recipient without a record:
  - Query Gmail Sent folder: "Do I have a message to this recipient today?"
  - If YES: backfill the missing record (system crashed mid-batch, record not written)
  - If NO: send normally (never sent or already handled)
- Graceful error handling: if Gmail query fails, proceeds with normal send
- Prevents duplicates from crash-recovery restarts
- 373 tests pass; includes 9 comprehensive recovery tests
- **Git:** `786f018 ✨ feat(send): gmail recovery on startup`

**Commit 4:** Integration Test for Recovery
- Simulate crash mid-batch (send to Alice & Bob, crash before recording)
- Verify restart only sends to missing recipients (Charlie only)
- Assert no duplicates in final state

**Effort:** ~8 hours (spread across Phase 1)

---

### Task 1.2: Remove Email Addresses from Logs
**Status:** NOT STARTED  
**P/S:** P=1, S=1 (privacy/compliance issue)  

**Problem:** User emails printed to logs stored on Render (external service).

**Solution:**
- Audit logs: `app/subscriber_manager.py` (5 calls), `scripts/migrate_subscribers.py` (7 calls)
- Replace specific addresses with generic: `"Added subscriber"` instead of `"Added subscriber alice@example.com"`
- Verify no regression with test suite

**Effort:** ~2 hours

---

### Task 1.3: Add JSON Schema Validation for Dispatch Rules
**Status:** NOT STARTED  
**P/S:** P=1, S=1 (prevent silent misconfiguration)  

**Problem:** Hand-written JSON dispatch rules (e.g., `"time": "6:00"` vs `"06:00"`) silently fail.

**Solution:**
- Create JSON schema for `dispatch_rules.json` validation
- Validate on every load in `job_dispatcher.py`
- Fail fast with clear error messages
- Add test: invalid rules → caught + clear error

**Files:** `dispatch_rules.json`, `job_dispatcher.py`  
**Effort:** ~3 hours

---

## Phase 2: Subscriber Database Integration (July 2026)

**Goal:** Move from hardcoded EMAIL_TO to database-backed subscriber management.  
**P/S Ratings:** P=1, S=2 (high priority, moderate implementation complexity)

### Task 2.1: Migrate from EMAIL_TO Environment Variable to Database
**Status:** DONE ✅  
**P/S:** P=1, S=2  

**Current Limitation:**
- Subscribers hardcoded in `EMAIL_TO` env var
- To add user: rebuild → redeploy → wait for state restore (15–30 min)
- Not scalable for real usage

**Solution:**
- Use existing `Subscriber` database schema (already exists but not used in prod)
- Remove hardcoded `EMAIL_TO` from all code paths
- Admin API endpoints (already exist!) to add/remove subscribers
- Changes take effect immediately (no deploy cycle)
- Fetch subscriber list on each send cycle

**Files to Modify:**
- `sjzl_daily_email.py` - fetch recipients from DB instead of env var
- `job_dispatcher.py` - pass subscriber list to send pipeline
- `app/models.py` - ensure Subscriber model is complete
- Tests - update fixtures to use DB

**Implementation Order:**
1. Add database query to fetch active subscribers
2. Update send pipeline to use subscriber list
3. Test with existing test DB fixtures
4. Remove EMAIL_TO env var references
5. Add regression test: verify send hits all DB subscribers

**Refinement:** Content source validation now uses `content_source_factory.get_available_sources()` dynamically instead of hardcoding ("ezoe", "wix"). This enables adding new content sources (e.g., stmn1) by only updating CONTENT_SOURCES in the factory—no subscriber manager changes needed. (Commit: 070ed1a)

**Effort:** ~12 hours (largest Phase 2 task)  
**Test:** End-to-end tested with stmn1 content source and 2 real email addresses, using database subscribers. Gmail recovery backfill working correctly to prevent duplicates.

---

### Task 2.2: Add Subscriber Management API Endpoints
**Status:** PARTIAL (endpoints may already exist)  
**P/S:** P=1, S=2  

**Required Endpoints:**
- `POST /api/subscribers` - Add new subscriber (email + name)
- `GET /api/subscribers` - List all active subscribers
- `DELETE /api/subscribers/{id}` - Remove subscriber
- `PATCH /api/subscribers/{id}` - Update subscriber (toggle active/inactive)

**Validation:**
- Email format validation
- No duplicate emails
- Admin auth required (already implemented)

**Effort:** ~4 hours (if endpoints don't exist; check first)

---

### Task 2.3: Subscriber Onboarding Flow
**Status:** NOT STARTED (out of scope for this phase if low priority)  
**P/S:** P=2, S=3 (can defer to Phase 4)  

**Optional:** Public-facing subscriber signup page:
- Simple form: name + email
- Email verification (optional for now)
- Unsubscribe link in emails (legal requirement)

**Decision:** Defer to Phase 4 if time is constrained.

**Effort:** ~8 hours (deferred)

---

### Task 2.4: (Bonus) Instant Test Send Button
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (testing/debugging, improves validation of Phase 2)

**Purpose:** Allow manual trigger of send flow from dashboard to test Phase 2 integration.

**Requirements:**
- Dashboard button: "Send Now" to manually trigger send cycle
- Configurable: choose content source + subscriber(s) to test
- Real send: actually sends emails to selected recipients
- Feedback: show success/error in UI
- Audit: log test sends separately (don't count as scheduled)

**API Endpoint:**
- `POST /api/test-send` - Accepts content_source, recipient(s), return message_id

**Files:**
- `app/main.py` - Add test send endpoint
- `app/templates/dashboard.html` - Add button + modal
- `app/static/test_send.js` - Handle UI interaction

**Benefits:**
- Verify Phase 2 end-to-end: DB → send → delivery tracking
- Faster iteration (no wait for scheduled send)
- Reduce testing burden during Phase 2 validation

**Effort:** ~4 hours

---

### Task 2.5: Add Display Names to Content Sources
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (UX improvement for signup form)

**Purpose:** Show user-friendly Chinese names instead of technical identifiers in signup form.

**Requirements:**
- Add `get_display_name()` class method to each content source
- Signup form uses display names instead of source IDs
- Dashboard/admin still uses technical names (ezoe, wix, stmn1) for clarity
- Mapping:
  - `wix` → "晨興聖言" (Morning Revival)
  - `stmn1` → "聖經之旅" (Bible Journey)
  - `ezoe` → "聖經之旅" (Bible Journey - alternative source, disabled)

**Implementation:**
- Modify each content source class: `ezoe_content_source.py`, `wix_content_source.py`, `stmn1_content_source.py`
- Update `/subscribe` page to use `source.get_display_name()` instead of source ID
- No database changes needed

**Files:**
- `ezoe_content_source.py`, `wix_content_source.py`, `stmn1_content_source.py` - Add `get_display_name()`
- `app/templates/dashboard.html` - Update signup form to use display names

**Effort:** ~1 hour

---

### Task 2.6: Disable EZOE Content Source
**Status:** NOT STARTED  
**P/S:** P=1, S=2 (required - EZOE blocked by anti-bot on production)

**Purpose:** Hide EZOE as signup option and prevent new subscriptions, since it's blocked in production. STMN1 serves same content as fallback.

**Requirements:**
- Add environment variable: `DISABLED_CONTENT_SOURCES=ezoe`
- Signup form filters out disabled sources
- API rejects signup for disabled sources
- Existing EZOE subscribers remain in database (soft delete via `.active` field if needed later)

**Implementation:**
- Modify `content_source_factory.py:get_available_sources()` to filter by `DISABLED_CONTENT_SOURCES` env var
- Existing validation in `subscriber_manager.py` automatically rejects disabled sources
- Set `DISABLED_CONTENT_SOURCES=ezoe` in production .env

**Files:**
- `content_source_factory.py` - Add disabled sources filtering
- `.env.example` - Document DISABLED_CONTENT_SOURCES variable

**Effort:** ~0.5 hours

---

### Task 2.7: Refactor send_email() to require recipients parameter
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (code quality, semantic clarity)

**Purpose:** Separate recipient determination from email sending. Currently send_email() both determines recipients (from database or env var) AND sends email, mixing concerns. Move recipient logic to callers (run_once, summary email, test send).

**Problem:** 
- send_email() shouldn't determine recipients—that's the caller's responsibility
- Summary email hacks environment variables to hijack EMAIL_TO (brittle)
- Semantic confusion: is send_email responsible for who gets the email?

**Solution:**
- Make `recipients` a required parameter to send_email()
- Remove RECIPIENT_SOURCE logic from send_email()
- Callers determine recipients first, then pass to send_email()
- Example: run_once() calls get_subscribers(source), then send_email(..., recipients=...)

**Implementation:**
- `sjzl_daily_email.py:send_email()` - Add recipients parameter, remove recipient determination logic
- `schedule_tasks.py:run_once()` - Fetch subscribers, pass to send_email()
- `schedule_tasks.py:_send_summary_email()` - Pass admin email list to send_email(), remove env var hacking

**Impact:**
- Cleaner separation of concerns
- More testable (no env var hijacking)
- More readable (explicit recipients at call site)
- Removes deprecated RECIPIENT_SOURCE="email" mode

**Files:**
- `sjzl_daily_email.py` - Refactor send_email() signature
- `schedule_tasks.py` - Update callers

**Effort:** ~2 hours

---

### Task 2.9: Make test sends completely side-effect-free
**Status:** IN PROGRESS  
**P/S:** P=3, S=3 (production safety, CRITICAL for reliability)

**Purpose:** Ensure test sends NEVER modify schedule status or any production state.

**Root Cause Identified:** 
- Test sends are changing schedule entry status to "sent"
- This blocks production sends from running the same day
- Users must manually revert to "pending" after each test
- TEST_MODE flag doesn't prevent schedule mutations

**Problem:** 
- Test send marks schedule as "sent" (blocking production)
- Can't run multiple test sends without manual intervention
- Test sends are NOT side-effect-free (they modify production state)
- Goal: run unlimited test sends without touching schedule or any production files

**Solution:**
- Add explicit check: skip schedule updates when TEST_MODE=1
- Ensure test mode:
  - ✓ Sends emails (only side effect)
  - ✗ Does NOT change schedule status
  - ✗ Does NOT modify schedule files
  - ✗ Does NOT touch delivery records
  - ✗ Does NOT modify state/
  - ✗ Does NOT modify any production files

**Implementation:**
- Find all places that call `mark_sent()` 
- Add guard: `if not os.getenv("TEST_MODE"): mark_sent(...)`
- Find all places that update schedule entry status
- Add TEST_MODE check before any schedule updates
- Update cron_runner._execute_job_from_rule() to skip schedule saves in TEST_MODE
- Create verification test to ensure schedule is unmodified after test send

**Key Locations to Protect:**
- schedule_manager.mark_sent()
- cron_runner.save_schedule() calls
- Any schedule.entry.status updates

**Behavior:**
```python
# When TEST_MODE=1:
# ✓ Email sent via Gmail API  
# ✗ Schedule NOT marked as sent
# ✗ Schedule status stays "pending"
# ✓ Can run unlimited test sends in one day
# ✓ Production send works immediately after test send
```

**Test case:**
- Set TEST_MODE=1
- Send test email
- Verify schedule entry status is still "pending"
- Verify no schedule files were modified
- Verify can send test again (no "already sent" blocking)

**Effort:** ~1.5 hours

---

### Task 2.8: Admin dashboard indicators for disabled sources
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (admin UX, visibility)

**Purpose:** Show disabled content sources in admin dashboard with clear indicators. Allow admin visibility and management while preventing users from selecting them.

**Problem:**
- User-facing signup hides disabled sources (good UX for users)
- But admin dashboard may be confusing if default source is disabled
- Jobs might reference disabled sources—admin needs visibility
- No warning if job tries to use disabled source

**Solution:**
- Dashboard shows disabled sources with "Disabled" badge
- Admin can still view/manage disabled sources
- Warn if job rule uses disabled source
- Gracefully handle job execution with disabled sources (error/skip)

**Implementation:**
- `app/main.py` - Add disabled source info to dashboard context
- `app/templates/dashboard.html` - Show disabled badge on content source selector
- `dispatch_rules_validator.py` - Warn if rule references disabled source
- `schedule_tasks.py:run_once()` - Handle disabled source gracefully

**Behavior:**
- Dashboard shows: "Content Source: 聖經之旅 (ezoe) [DISABLED]"
- Job with disabled source shows warning: "⚠️ This job uses disabled source EZOE"
- Job execution: Skip send or error gracefully

**Effort:** ~1.5 hours

---

## Phase 3: Dashboard & Observability (August 2026)

**Goal:** Improve admin visibility and system monitoring.  
**P/S Ratings:** P=2–3, S=2 (nice-to-have but valuable for maintainability)

### Task 3.0: Data Integrity & Error Reporting (7 Verified Issues)
**Status:** NOT STARTED  
**P/S:** P=2, S=1 (data accuracy, dashboard reliability)

**Goal:** Fix 7 verified data integrity issues that affect dashboard accuracy and user experience.

**7 Issues to Fix:**

**CRITICAL (1):**
1. **Status vs exit code contradiction** — `cron_runner.py:327-329`
   - During retries, dashboard shows status="running" + exit_code=1 simultaneously (confusing)
   - Fix: Only set exit_code when status is "success" or "failed", not during intermediate retries

**HIGH (4):**
2. **Missing metadata for timeout/exception** — `cron_runner.py:340-346, 356-362`
   - Timeout and exception failures lack debug metadata (command, timeout, stream lengths)
   - Fix: Add same `metadata` dict to all update_job() calls (not just exit_code failures)

3. **Recipient count placeholder** — `run_daily_stateful_ezoe.sh:70`
   - Shows string "configured_via_env" instead of actual recipient count
   - Fix: Extract actual count from EMAIL_TO env var or delivery result

4. **Partial delivery as success** — `sjzl_daily_email.py:549-553, 739, 796`
   - Job returns exit 0 even if 70% of recipients fail (3/10 sent, 7/10 failed)
   - Fix: Return exit code 2 (partial success) or 1 (failure) based on delivery rate

5. **Race condition in manual job run** — `cron_runner.py:448`
   - Job executed but may return None if not yet in history
   - Fix: Call `get_recent_executions()` once, store result, reuse it

**MEDIUM (2):**
6. **Duplicate error logging** — `cron_runner.py:337-338, 341-342`
   - Timeout errors appear twice in logs (append + extend duplication)
   - Fix: Pass complete job_result.logs to update_job() instead of [error_msg]

7. **30-day data loss** — `job_tracker.py:120-123`
   - Jobs older than 30 days silently deleted on restart (no audit trail)
   - Fix: Document retention policy OR implement archive rotation OR extend to 90 days

**Files to Modify:**
- `app/cron_runner.py` — Retry state, metadata, race condition, error logging
- `run_daily_stateful_ezoe.sh` — Recipient count placeholder
- `sjzl_daily_email.py` — Partial delivery handling
- `app/job_tracker.py` — Data retention policy

**Impact:**
- Dashboard displays accurate job status (no contradictions)
- Better debugging info for timeout/exception failures
- Partial delivery failures are visible/alertable
- No silent data loss of historical jobs
- Cleaner, non-duplicate logs

**Effort:** ~4 hours (comprehensive fix across 4 files)

---

### Task 3.1: Enhance Job History Dashboard
**Status:** EXISTS (partial)  
**P/S:** P=2, S=2  

**Current State:**
- `/api/jobs/recent` endpoint exists
- Job history displayed in notification center
- **Missing:** Error details, failure highlights, admin alerts

**Enhancement:**
- Show job error messages in UI (currently hidden)
- Highlight failed jobs in red/warning color
- Fix relative time display: show "yesterday" instead of "16 hours ago" for older entries
- Add admin Slack webhook for critical failures (optional)
- Allow users to check personal delivery status (view their sent date)

**Files:**
- `app/main.py` - API endpoints (already exist, just enhance)
- `app/templates/dashboard.html` - UI improvements
- `app/static/notification.js` - Relative time formatting logic

**Effort:** ~6 hours

---

### Task 3.2: Email Delivery Status Page (User-Facing)
**Status:** NOT STARTED  
**P/S:** P=2, S=3 (cosmetic, user-facing)  

**Feature:** Allow subscribers to check if today's email was delivered.

**Implementation:**
- Simple page: `/deliver/status?email=user@example.com`
- Query: "Was an email sent to this address today?"
- Show: "✓ Delivered at 06:05 AM" or "⏳ Scheduled for 06:00 AM"
- No auth required (email is the credential)

**Effort:** ~4 hours (can defer to Phase 4)

---

### Task 3.3: Real-Time Dashboard Updates with AJAX
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (UX improvement, avoids page reloads)

**Problem:** Dashboard reloads entire page when updating schedule entries or running actions, poor user experience.

**Solution:**
- Replace full page reloads with AJAX fetch calls
- Real-time updates without leaving the page
- Show loading states during requests
- Display success/error messages inline
- Preserve scroll position and form state

**Implementation:**
- Refactor dispatch_rules.js to use fetch() instead of form submission
- Add loading spinners during async operations
- Update modal feedback handlers for AJAX responses
- Ensure error states display clearly

**Files:**
- `app/static/dispatch_rules.js` - AJAX refactor for rule updates
- `app/static/calendar.js` - AJAX for schedule entry updates
- `app/static/test_send.js` - Already uses fetch, ensure consistency
- `app/templates/dashboard.html` - Add loading states/spinners

**Benefits:**
- Smooth UX: no page reload flicker
- Faster feedback: immediate visual response
- Preserves context: user stays in same view
- Better for mobile: less data bandwidth

**Effort:** ~6 hours

---

### Task 3.4: Dashboard UX Improvements
**Status:** NOT STARTED  
**P/S:** P=3, S=3 (polish, low priority)  

**Improvements:**
- Dark mode support (cosmetic)
- Refined loading states and spinners
- Better error message styling
- Form validation feedback

**Effort:** ~8 hours (can defer to Phase 4 if constrained)

---

## Pre-Phase 4: Privacy & Security (Required Before Production)

### Task PRE-4.1: Email Verification for Information Disclosure Endpoints
**Status:** FLAGGED (not yet started)  
**P/S:** P=1, S=1 (CRITICAL privacy/security requirement)  
**Required Before:** Phase 4 (production launch)

**Privacy Issue Identified:**
Both `/subscribe` and `/delivery-status` pages allow anyone to enter an email and potentially learn:
- **On /subscribe:** Whether an email is already subscribed (email enumeration attack)
- **On /delivery-status:** Full delivery history for any email (information disclosure + enumeration)

Combined with email enumeration, an attacker can:
1. Gather list of valid emails
2. Query delivery records for each
3. Infer subscriber patterns and behavior

**Solution: Email Verification Flow**
Before revealing any information (subscription status or delivery records), require email verification:
1. User enters email on `/subscribe` or `/delivery-status`
2. System sends verification code/link to email address
3. User clicks link or enters code to verify ownership
4. Only after verification does user see:
   - Subscription confirmation (on /subscribe)
   - Delivery history (on /delivery-status)

**Implementation:**
- Create verification token system (random code + expiration, e.g., 15 min)
- Store tokens in database (or encrypted file with TTL)
- Add `/verify?token=XXX` endpoint to confirm ownership
- Modify `/subscribe` and `/delivery-status` to require verification step
- Only POST after verification confirmed
- Rate limit verification requests (5/hour per email)

**Database Changes:**
- Add `verification_tokens` table (or similar):
  - `token` (unique, indexed)
  - `email` (lower-cased)
  - `action` (subscribe | delivery-status)
  - `created_at`
  - `expires_at`
  - `verified_at` (nullable, set on verification)

**Affected Endpoints:**
- `GET /subscribe` → Add verification step
- `POST /api/public/subscribe` → Only accept verified emails
- `GET /delivery-status` → Add verification step  
- `GET /api/deliver/status` → Only accept verified emails
- `GET /unsubscribe` → Consider verification here too (lower priority)
- (NEW) `POST /api/verify-email` → Verify token and set session/cookie
- (NEW) `GET /verify?token=XXX` → Confirmation page/redirect

**Benefits:**
- Eliminates email enumeration attack surface
- Proves email ownership before revealing data
- Complies with privacy-by-design principles
- Production-safe (no information leakage)

**Effort:** ~6-8 hours (token system, email sending, form flow)

---

## Phase 4: Email Formatting & Polish (September 2026)

**Goal:** Improve email appearance and prepare for launch.  
**P/S Ratings:** P=2–3, S=2–3 (cosmetic but important for user experience)

### Task 4.0: Full Mobile Support for Dashboard
**Status:** NOT STARTED  
**P/S:** P=2, S=3 (Polish: responsive mobile UI, phase 4 enhancement)

**Problem:** Dashboard relies on keyboard shortcuts and desktop-style interactions; no mobile support for small screens.

**Solution:**
- Responsive design for tablets and phones
- Touch-friendly buttons (larger touch targets)
- Dropdown/mobile menu for navigation
- Optimize modals for small screens
- Mobile-friendly form inputs
- Flexible layout (single column on mobile, multi-column on desktop)

**Implementation:**
- Add CSS media queries for mobile breakpoints (375px, 768px, 1024px)
- Refactor navigation for mobile (hamburger menu on small screens)
- Adjust modal sizing and positioning for mobile
- Make action buttons more touch-friendly
- Test on real mobile devices or browser DevTools

**Files:**
- `app/templates/dashboard.html` - Mobile-responsive layout
- `app/static/css/` (new or existing) - Media queries and responsive styles
- `app/static/calendar.js` - Mobile event handling
- `app/static/dispatch_rules.js` - Mobile interaction patterns

**Benefits:**
- Dashboard usable on phones/tablets
- Better accessibility (larger touch targets)
- Professional appearance on all devices
- Better mobile user experience

**Effort:** ~12 hours (significant refactor)

---

### Task 4.1: Fix Persistent Messages in Dashboard UI
**Status:** NOT STARTED  
**P/S:** P=2, S=2 (DX improvement, affects all forms/modals)

**Current Problem:** Server messages sent via message callback (error, success notifications) persist in page state and reappear after refresh. Examples:
- "Failed to update entry"
- "Cross-site attack message"  
- Old error/success messages from previous actions

**Expected Behavior:** Messages should be transient (auto-dismiss after 3-5 seconds) and cleared on page navigation/refresh. They should NOT persist across page reloads.

**Current Message System:**
- Flash messages (Jinja2 server-side): Rendered in HTML, no auto-dismiss
- Feedback elements (client-side): dispatch_rules.js and test_send.js use `setFeedback()` with 3-5s auto-dismiss
- Notifications (localStorage): Job history with acknowledged state

**Root Cause:** Messages stored in DOM state or localStorage without clear lifecycle management tied to page load.

**Fix:**
- Flash messages: Add client-side auto-dismiss timeout (3-5 seconds)
- Feedback elements: Ensure consistent auto-dismiss across all modals/overlays
- Clear message queue on page load (don't persist)
- Use sessionStorage instead of localStorage for transient state
- Ensure server messages don't leak into page state persistence

**Files:**
- `app/templates/dashboard.html` - Flash message section and feedback elements
- `app/static/notification.js` - Message lifecycle management
- `app/static/dispatch_rules.js` - Feedback handling (reference implementation)
- `app/static/test_send.js` - Feedback handling (reference implementation)

**Benefits:**
- Cleaner UX: no stale error messages
- User clarity: messages disappear after acknowledgment
- Consistency: all messages follow same transient behavior
- Better DX: reduces confusion from old messages

**Effort:** ~4 hours

---

### Task 4.1: Email HTML/CSS Improvements
**Status:** NOT STARTED  
**P/S:** P=3, S=2  

**Current State:** Emails have basic HTML + scoped CSS from `sjzl_daily_email.py`

**Enhancements:**
- Improve email template typography (better fonts, spacing)
- Add dark mode CSS (media query: `prefers-color-scheme: dark`)
- Better mobile responsiveness (max-width container)
- Add company branding (logo, footer with unsubscribe link)

**Files:**
- `sjzl_daily_email.py` - email template CSS

**Effort:** ~6 hours

---

### Task 4.2: Expand Content Sources (Channel Management)
**Status:** NOT STARTED  
**P/S:** P=3, S=3 (future extensibility, low priority)  

**Current Sources:** EZOe, Wix, Legacy (SJZL)

**Optional Future Sources:**
- Bible.com API
- YouVersion Verse of the Day
- Custom RSS feeds
- User-provided content

**Decision:** Document the factory pattern and make it easy to add new sources, but don't implement new sources yet.

**Files:** `content_source_factory.py`, `content_source.py`  
**Effort:** ~4 hours (documentation + example)

---

### Task 4.3: Documentation & Architecture Guide
**Status:** PARTIAL (codebase analysis exists)  
**P/S:** P=3, S=3  

**Deliverables:**
- README.md with setup instructions
- Architecture overview (can re-use codebase analysis)
- Admin guide (how to manage subscribers, view logs, troubleshoot)
- Developer guide (how to add new content sources, extend API)

**Files:**
- README.md (new)
- docs/ARCHITECTURE.md (from codebase analysis)
- docs/ADMIN_GUIDE.md (new)
- docs/DEVELOPER_GUIDE.md (new)

**Effort:** ~6 hours

---

### Task 4.4: Deployment & Scaling Preparation
**Status:** NOT STARTED  
**P/S:** P=3, S=2 (future-proofing)  

**Forward Planning:** From codebase analysis, document migration path:
- Phase 1: Keep JSON, migrate schedule to database
- Phase 2: Add Celery job queue for email throughput
- Phase 3: Distributed locking with Redis
- Phase 4: Multiple instances + load balancer

**Deliverables:**
- Scalability roadmap document
- Database migration scripts (template)
- Deployment checklist

**Effort:** ~4 hours (planning doc only, no implementation)

---

## Timeline Summary

| Month | Phase | Focus | Key Deliverables |
|-------|-------|-------|------------------|
| **June** | Phase 1 | Reliability | ✅ Delivery tracking (4 commits), Privacy fixes, Config validation |
| **July** | Phase 2 | Subscribers | Migrate to DB, API endpoints, user onboarding (optional) |
| **August** | Phase 3 | Dashboard | Job history UI, user status page, UX polish |
| **September** | Phase 4 | Polish | Email formatting, content sources, docs, scalability plan |

---

## Effort Allocation

**Total Estimated Effort:** ~103 hours

| Phase | Hours | % |
|-------|-------|---|
| Phase 1 (Reliability) | 13 | 13% |
| Phase 2 (Subscribers) | 24 | 23% |
| Phase 3 (Dashboard) | 24 | 23% |
| Phase 4 (Polish) | 42 | 41% |

**Realistic Weekly Pace:** ~5 hours/week = ~20 weeks total  
**4-Month Window:** ~16 weeks available  
→ **Recommend deferring Phase 4 tasks (polish) to Phase 4.5 (October+)**

---

## Dependencies & Constraints

### Critical Dependencies
- **Phase 1 → Phase 2:** Must complete delivery tracking before adding subscribers (ensures no duplicate emails even with DB changes)
- **Phase 2 → Production:** Must have subscriber DB working before real users

### External Constraints
- Gmail API rate limits (backfill during recovery)
- Database connection pooling (already configured in `models.py`)
- Render platform limitations (ENV VAR limits, log storage)

### Testing Requirements
- All 341 existing tests must pass after changes
- Add new integration tests for each phase
- Manual testing on Render staging environment

---

## Success Criteria

By end of September 2026:

- ✅ **Phase 1:** Zero duplicate emails, no user privacy leaks, config validation
- ✅ **Phase 2:** Production-ready subscriber management (no EMAIL_TO env var)
- ✅ **Phase 3:** Admin dashboard shows job history and errors clearly
- ✅ **Phase 4:** Emails look professional, documentation complete, scalability roadmap defined

---

## Notes

### From Codebase Analysis
The system is well-architected with strong separation of concerns. Key insights:
- **Factory pattern** makes adding content sources trivial
- **JSON persistence** is simple but will need DB migration at ~100k users
- **Job dispatcher** is flexible (works with cron or containers)
- **OAuth2 integration** with Gmail is secure and complete

### Recommendation
Focus Phase 1–2 on production readiness, defer cosmetic Phase 4 work if time is tight. The system is already more reliable and well-designed than most personal-scale projects.

---

## How to Use This Plan

1. **Each week:** Pick 1–2 tasks from the current phase
2. **Create atomic commits:** 1 commit per task or subtask (follow conventional commits)
3. **Tests must pass:** Run full suite before committing
4. **Update CLAUDE.md:** Move "Current Work" section here once tasks start
5. **Document decisions:** Add notes in this file as you learn

---

**Next Steps:**
1. ✅ Read this plan
2. 📌 Start Commit 2 (Task 1.1): Store message IDs in schedule JSON
3. 🧪 Run tests after each commit
4. 📝 Track progress in this file (update status column)
