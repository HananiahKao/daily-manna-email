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
- [ ] **2.1** Migrate from EMAIL_TO env var to database
- [ ] **2.2** Add subscriber management API endpoints
- [ ] **2.3** Subscriber onboarding flow (optional, can defer)

**Phase 2 Progress:** 0/3 tasks complete (0%)

### Phase 3: Dashboard & Observability (August) — P=2, S=2
- [ ] **3.1** Enhance job history dashboard
- [ ] **3.2** Email delivery status page (user-facing)
- [ ] **3.3** Dashboard UX improvements

**Phase 3 Progress:** 0/3 tasks complete (0%)

### Phase 4: Email Formatting & Polish (September) — P=3, S=2–3
- [ ] **4.1** Email HTML/CSS improvements
- [ ] **4.2** Expand content sources (channel management)
- [ ] **4.3** Documentation & architecture guide
- [ ] **4.4** Deployment & scaling preparation

**Phase 4 Progress:** 0/4 tasks complete (0%)

---

**Overall Progress:** 6/16 tasks complete (38%) | ⏳ Phase 2 Ready

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
**Status:** NOT STARTED  
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

**Effort:** ~12 hours (largest Phase 2 task)

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

## Phase 3: Dashboard & Observability (August 2026)

**Goal:** Improve admin visibility and system monitoring.  
**P/S Ratings:** P=2–3, S=2 (nice-to-have but valuable for maintainability)

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
- Add admin Slack webhook for critical failures (optional)
- Allow users to check personal delivery status (view their sent date)

**Files:**
- `app/main.py` - API endpoints (already exist, just enhance)
- `app/templates/dashboard.html` - UI improvements

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

### Task 3.3: Dashboard UX Improvements
**Status:** NOT STARTED  
**P/S:** P=3, S=3 (polish, low priority)  

**Improvements:**
- Responsive design (mobile-friendly dashboard)
- Dark mode support (cosmetic)
- Loading states and spinners
- Better error messages in forms

**Effort:** ~8 hours (defer to Phase 4 if constrained)

---

## Phase 4: Email Formatting & Polish (September 2026)

**Goal:** Improve email appearance and prepare for launch.  
**P/S Ratings:** P=3, S=2–3 (cosmetic but important for user experience)

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

**Total Estimated Effort:** ~85 hours

| Phase | Hours | % |
|-------|-------|---|
| Phase 1 (Reliability) | 13 | 15% |
| Phase 2 (Subscribers) | 24 | 28% |
| Phase 3 (Dashboard) | 18 | 21% |
| Phase 4 (Polish) | 30 | 36% |

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
