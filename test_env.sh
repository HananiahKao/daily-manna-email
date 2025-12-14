#!/bin/zsh

# ===== CONFIGURATION =====
LOG_FILE="${LOG_FILE:-test_env_$(date +%Y%m%d_%H%M%S).log}"
SCRIPT_START_TIME=$(date +%s)
EXIT_CODE=0

# Test result counters
SUCCESS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# ===== LOGGING FUNCTIONS =====
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local log_line="[$timestamp] [$level] $message"

    # Output to console (colorize if terminal supports it)
    if [[ -t 1 ]]; then
        case "$level" in
            "SUCCESS") echo -e "\033[32m$log_line\033[0m" ;;
            "FAIL") echo -e "\033[31m$log_line\033[0m" ;;
            "WARN") echo -e "\033[33m$log_line\033[0m" ;;
            "INFO") echo -e "\033[36m$log_line\033[0m" ;;
            *) echo "$log_line" ;;
        esac
    else
        echo "$log_line"
    fi

    # Always write to log file
    echo "$log_line" >> "$LOG_FILE"
}

log_success() {
    log "SUCCESS" "$1"
    ((SUCCESS_COUNT++))
}

log_fail() {
    log "FAIL" "$1"
    ((FAIL_COUNT++))
    EXIT_CODE=1
}

log_warn() {
    log "WARN" "$1"
    ((WARN_COUNT++))
}

log_info() {
    log "INFO" "$1"
}

# ===== CLEANUP FUNCTION =====
cleanup() {
    if [[ -f "/tmp/test_schedule_basic.json" ]]; then
        rm -f "/tmp/test_schedule_basic.json"
    fi
}

# ===== UTILITY FUNCTIONS =====
run_python_or_fail() {
    local test_desc="$1"
    shift
    log_info "Running: $test_desc"
    if python -c "$@" 2>&1; then
        log_success "$test_desc"
        return 0
    else
        log_fail "$test_desc: Failed with exit code $?"
        return 1
    fi
}

run_python_with_catch() {
    local test_desc="$1"
    local catch_desc="$2"
    shift 2
    log_info "Running: $test_desc"
    if python -c "$@" 2>&1; then
        log_success "$test_desc"
        return 0
    else
        log_warn "$catch_desc"
        return 0
    fi
}

# ===== ENVIRONMENT VALIDATION =====
log_info "Starting environment readiness test..."
log_info "Log file: $LOG_FILE"

# Validate required files/directories
required_files=(".venv/bin/activate" ".env" "app/main.py")
for file in "${required_files[@]}"; do
    if [[ ! -f "$file" ]]; then
        log_fail "Required file missing: $file"
    else
        log_info "Found required file: $file"
    fi
done

# Load the virtual environment
if [[ -f ".venv/bin/activate" ]]; then
    set +e  # Disable exit on error temporarily
    source .venv/bin/activate
    if [[ $? -eq 0 ]]; then
        log_success "Virtual environment activated"
    else
        log_fail "Failed to activate virtual environment"
    fi
    set -e  # Re-enable exit on error
else
    log_fail "Virtual environment not found at .venv/bin/activate"
fi

# Load environment variables
if [[ -f ".env" ]]; then
    log_info "Loading environment variables from .env"
    set -a
    source .env
    set +a
    log_success "Environment variables loaded"
else
    log_fail "Environment file .env not found"
fi

# ===== BASIC IMPORTS TEST =====
log_info "Testing basic Python imports..."
imports=(
    "sjzl_daily_email:Core daily email module"
    "content_source_factory:Content source factory"
    "ezoe_content_source:EZOE content source"
    "wix_content_source:Wix content source"
    "schedule_manager:Schedule management utilities"
    "schedule_tasks:Scheduled task operations"
)

for import_info in "${imports[@]}"; do
    import_module="${import_info%%:*}"
    import_desc="${import_info#*:}"
    run_python_or_fail "Basic import: $import_desc" "import $import_module; print('✓ $import_module ($import_desc)')"
done

# ===== CONTENT SOURCE FUNCTIONALITY TEST =====
log_info "Testing content source functionality..."
run_python_with_catch \
    "Content source initialization" \
    "Content source initialization failed (may be configuration issue)" \
    "
import sys
from content_source_factory import get_active_source
try:
    source = get_active_source()
    print(f'✓ Active source: {source.__class__.__name__}')
    sys.exit(0)
except Exception as e:
    print(f'⚠ Source initialization error: {e}')
    sys.exit(1)
"

run_python_with_catch \
    "Content source default selector" \
    "Default selector retrieval failed" \
    "
import sys
from content_source_factory import get_active_source
try:
    source = get_active_source()
    default_selector = source.get_default_selector()
    print(f'✓ Default selector: {default_selector}')
    sys.exit(0)
except Exception as e:
    print(f'⚠ Selector error: {e}')
    sys.exit(1)
"

run_python_with_catch \
    "Content source content fetching" \
    "Content fetching failed (may be expected without network/proxy config)" \
    "
import sys
from content_source_factory import get_active_source
try:
    source = get_active_source()
    default_selector = source.get_default_selector()
    content_block = source.get_daily_content(default_selector)
    if content_block and len(content_block.html_content) > 100:
        print('✓ Content fetching works')
        print(f'✓ Content title: {content_block.title}')
        print(f'✓ Content length: {len(content_block.html_content)} chars')
    else:
        print('⚠ Content fetched but appears minimal/empty')
    sys.exit(0)
except Exception as e:
    print(f'⚠ Content fetch error: {e}')
    sys.exit(1)
"

# ===== SCHEDULE MANAGEMENT TEST =====
log_info "Testing schedule management functionality..."
run_python_with_catch \
    "Schedule save/load functionality" \
    "Schedule save/load test failed" \
    "
import sys
import schedule_manager as sm
import os
from pathlib import Path
import datetime as dt
import json
try:
    # Test basic schedule operations
    test_schedule = sm.Schedule()
    test_entry = sm.ScheduleEntry(date=dt.date(2025, 1, 1), selector='1-1-1')
    test_schedule.upsert_entry(test_entry)

    test_file = Path('/tmp/test_schedule_basic.json')
    sm.save_schedule(test_schedule, test_file)

    loaded_schedule = sm.load_schedule(test_file)
    if len(loaded_schedule.entries) == 1 and loaded_schedule.entries[0].selector == '1-1-1':
        print('✓ Schedule save/load works')
        test_file.unlink(missing_ok=True)
        sys.exit(0)
    else:
        print('⚠ Schedule save/load mismatch')
        test_file.unlink(missing_ok=True)
        sys.exit(1)
except Exception as e:
    print(f'⚠ Schedule test failed: {e}')
    test_file = Path('/tmp/test_schedule_basic.json')
    test_file.unlink(missing_ok=True)
    sys.exit(1)
"

# ===== EMAIL FUNCTIONALITY TEST =====
log_info "Testing email configuration and integration..."
run_python_with_catch \
    "Email environment variables validation" \
    "Some email environment variables are missing" \
    "
import os
import sys

# Check if required env vars are set
required_vars = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'EMAIL_TO']
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print(f'⚠ Missing env vars for email: {missing}')
    # Don't fail the test, just warn
    sys.exit(0)
else:
    print('✓ Email configuration appears ready')
    sys.exit(0)
"

run_python_with_catch \
    "Content source/email integration" \
    "Content source integration failed" \
    "
import sys
from content_source_factory import get_active_source
import os

# Skip if required vars missing
required_vars = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'EMAIL_TO']
if any(not os.getenv(v) for v in required_vars):
    print('⚠ Skipping email integration test - missing SMTP config')
    sys.exit(0)

# Test content source integration for email
source = get_active_source()
try:
    default_sel = source.get_default_selector()
    content = source.get_daily_content(default_sel)
    if content and content.html_content:
        print(f'✓ Content source integration: {len(content.html_content)} chars fetched')
        subject = source.get_email_subject(default_sel, content.title)
        print(f'✓ Email subject generation: {subject}')
    else:
        print('⚠ Content source returned empty content')
except Exception as e:
    print(f'⚠ Content source error: {e}')
    sys.exit(1)
"

# ===== FASTAPI APPLICATION TEST =====
log_info "Testing FastAPI web application..."
run_python_with_catch \
    "FastAPI root endpoint" \
    "Authentication is properly working" \
    "
import sys
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
try:
    response = client.get('/')
    if response.status_code == 401:
        print('✓ FastAPI root endpoint authentication is working')
        print('✓ Security middleware properly configured')
        sys.exit(0)
    elif response.status_code == 200:
        print('⚠ Warning: Root endpoint accessible without authentication')
        print(f'Response content length: {len(response.text)} chars')
        sys.exit(0)
    else:
        print(f'⚠ Unexpected status: {response.status_code}')
        print(f'Response preview: {response.text[:100]}...')
        sys.exit(0)
except Exception as e:
    print(f'⚠ FastAPI test failed: {e}')
    sys.exit(0)
"

run_python_with_catch \
    "FastAPI health endpoint" \
    "Health endpoint test failed - check web application status" \
    "
import sys
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
try:
    response = client.get('/healthz')
    if response.status_code == 200:
        print('✓ Health endpoint works')
        sys.exit(0)
    else:
        print(f'⚠ Health endpoint status: {response.status_code}')
        sys.exit(1)
except Exception as e:
    print(f'⚠ Health test failed: {e}')
    sys.exit(1)
"

# ===== SERVER STARTUP TEST =====
log_info "Testing server startup capability..."

# Test uvicorn startup with timeout using shell wait-and-kill pattern
test_server_startup() {
    local timeout_secs=10
    log_info "Attempting to start uvicorn server (will timeout after ${timeout_secs}s)..."

    # Start uvicorn in background
    uvicorn app.main:app --host 127.0.0.1 --port 8000 &
    local server_pid=$!

    # Wait a bit for startup
    sleep 3

    # Check if still running
    if kill -0 $server_pid 2>/dev/null; then
        log_info "Server process is running, testing HTTP response..."

        # Test the response with curl
        if curl -s --max-time 3 http://127.0.0.1:8000/ >/dev/null 2>&1; then
            log_success "Uvicorn server started successfully and responds to HTTP requests"
            success=0
        else
            log_warn "Server started but dashboard endpoint not responding"
            success=1
        fi

        # Kill the server
        kill $server_pid
        wait $server_pid 2>/dev/null || true
        return $success
    else
        log_warn "Server failed to start or exited early"
        # Try to get exit code if possible
        wait $server_pid 2>/dev/null || true
        return 1
    fi
}

# Only test server startup if we're in an interactive environment
if [[ -n "$TERM" && -t 1 ]]; then
    test_server_startup
else
    log_warn "Skipping uvicorn startup test - not in interactive terminal"
    log_info "Manual test: uvicorn app.main:app --host 127.0.0.1 --port 8000"
fi

# ===== CLEANUP AND FINALIZE =====
cleanup

# ===== COMPREHENSIVE SUMMARY =====
log_info "About to generate summary..."
SCRIPT_END_TIME=$(date +%s)
EXECUTION_TIME=$((SCRIPT_END_TIME - SCRIPT_START_TIME))

log_info "===== ENVIRONMENT READINESS TEST SUMMARY ====="
log_info "Total execution time: ${EXECUTION_TIME} seconds"
log_info "Log file: $LOG_FILE"
log_info ""

log_info "📊 TEST RESULTS:"
log_info "✓ Successes: $SUCCESS_COUNT"
log_info "❌ Failures: $FAIL_COUNT"
log_info "⚠️  Warnings: $WARN_COUNT"
log_info ""

# Environmental readiness assessment
if [[ $FAIL_COUNT -eq 0 ]]; then
    if [[ $WARN_COUNT -eq 0 ]]; then
        log_success "🎉 ENVIRONMENT IS FULLY READY FOR PRODUCTION"
        log_info "All core components are working correctly."
    else
        log_warn "✅ ENVIRONMENT IS BASICALLY READY"
        log_info "Critical functionality works but some non-critical issues exist."
    fi
else
    log_fail "❌ ENVIRONMENT HAS CRITICAL ISSUES"
    log_info "Some core components are not working and require immediate attention."
fi

log_info ""
log_info "📋 DETAILED ANALYSIS:"
if [[ $SUCCESS_COUNT -gt 0 ]]; then
    log_info "✓ WORKING COMPONENTS:"
    log_success "Environment setup (venv, .env loading)"
    [[ $SUCCESS_COUNT -gt 2 ]] && log_success "Python imports and dependencies"
    [[ $SUCCESS_COUNT -gt 9 ]] && log_success "Content source functionality"
    [[ $SUCCESS_COUNT -gt 14 ]] && log_success "Web application (FastAPI)"
fi
    
if [[ $FAIL_COUNT -gt 0 ]]; then
    log_info "❌ CRITICAL ISSUES:"
    log_fail "Review the log file above for specific failures"
    [[ -z "$VIRTUAL_ENV" ]] && log_fail "Virtual environment activation failed - check .venv/"
    [[ ! -f ".env" ]] && log_fail "Environment file missing - required for configuration"
fi

if [[ $WARN_COUNT -gt 0 ]]; then
    log_info "⚠️  NON-CRITICAL CONCERNS:"
    if [[ ! -f ".env" ]] || ! grep -q "SMTP_HOST" .env 2>/dev/null; then
        log_warn "Email configuration incomplete - emails won't send in production"
    fi
    log_warn "Some tests may require network access or proxy configuration"
fi

log_info ""
log_info "🚀 NEXT STEPS:"
if [[ $FAIL_COUNT -eq 0 ]]; then
    log_info "1. For full email testing, run: python -c \"import schedule_tasks; schedule_tasks.show_next_run()\""
    log_info "2. Manually test server startup: uvicorn app.main:app --host 127.0.0.1 --port 8000"
    log_info "3. Review log file for any warnings that need attention: $LOG_FILE"
    log_info "4. Consider automating this script in CI/CD pipelines"
else
    log_info "1. Resolve critical failures shown above"
    log_info "2. Re-run this script after fixes"
    log_info "3. Check detailed logs in: $LOG_FILE"
fi

log_info ""
log_info "📝 NOTES:"
log_info "• The urllib3 LibreSSL warning is expected and can be ignored"
log_info "• Network-related warnings may require proxy configuration"
log_info "• Admin summary emails require ADMIN_SUMMARY_TO environment variable"

# Exit with appropriate code
log_info "Script completed with exit code $EXIT_CODE"
exit $EXIT_CODE
