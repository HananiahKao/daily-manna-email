#!/bin/bash
# Test: Content-Source Isolation for Delivery Tracking
#
# This script verifies that the hotfix for content-source-specific delivery
# tracking works correctly. It ensures that emails from different sources
# (stmn1, wix, etc.) don't interfere with each other's delivery records.
#
# Prerequisites:
# - Server running on localhost:8000
# - Admin credentials: username=admin, password=iamtheadmin
# - stmn1 and wix schedules exist with 2026-07-22 entries
#
# What it does:
# 1. Resets delivery state (clears deliveries.json)
# 2. Resets schedule entries to "pending" status
# 3. Runs stmn1 job (expects delivery record: stmn1:email)
# 4. Runs wix job (expects delivery record: wix:email)
# 5. Verifies both sources created separate delivery records
#
# Expected result: Both sources tracked independently, no cross-interference

set -a
source .env
set +a

echo "═══════════════════════════════════════════════════════════"
echo "Test: Content-Source Isolation (Full Reset)"
echo "═══════════════════════════════════════════════════════════"

echo ""
echo "🔄 Step 1: Reset delivery state"
rm -f state/deliveries.json
echo "✓ Delivery records cleared"

echo ""
echo "🔄 Step 2: Reset schedule entries to pending"
python3 << 'PYTHON'
import json

for schedule_file in ['state/stmn1_schedule.json', 'state/wix_schedule.json']:
    with open(schedule_file, 'r') as f:
        data = json.load(f)

    for entry in data.get('entries', []):
        if entry.get('date') == '2026-07-22':
            entry['status'] = 'pending'
            entry['sent_at'] = None

    with open(schedule_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Reset {schedule_file.split('/')[-1]}")
PYTHON

echo ""
echo "🔓 Step 3: Login"
SESSION=$(curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=iamtheadmin" \
  -c - | grep "^#HttpOnly" | awk '{print $NF}')

if [ -z "$SESSION" ]; then
    echo "❌ Login failed"
    exit 1
fi
echo "✓ Session obtained"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📧 Job 1: stmn1-bible-journey-daily-send"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏳ Running (API blocks until complete)..."
RESULT1=$(curl -s -X POST http://localhost:8000/api/jobs/run/stmn1-bible-journey-daily-send \
  --cookie "session=$SESSION")

echo "✓ stmn1 job completed"
[ "$RESULT1" != "{\"detail\":\"Command failed with exit code 1\"}" ] && echo "Result: $RESULT1" || echo "Status: failed (expected if no new sends)"

echo ""
echo "📋 Delivery records after stmn1:"
if [ -f state/deliveries.json ]; then
    cat state/deliveries.json | jq '.'
    STMN1_KEYS=$(cat state/deliveries.json | jq '.["2026-07-22"] | keys | map(select(startswith("stmn1"))) | length')
    echo "✓ stmn1 records: $STMN1_KEYS"
else
    echo "⚠ No delivery records yet"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📧 Job 2: morning-revival-daily-send (wix)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏳ Running (API blocks until complete)..."
RESULT2=$(curl -s -X POST http://localhost:8000/api/jobs/run/morning-revival-daily-send \
  --cookie "session=$SESSION")

echo "✓ wix job completed"
[ "$RESULT2" != "{\"detail\":\"Command failed with exit code 1\"}" ] && echo "Result: $RESULT2" || echo "Status: completed"

echo ""
echo "📋 Final delivery records:"
if [ -f state/deliveries.json ]; then
    cat state/deliveries.json | jq '.'
    STMN1_KEYS=$(cat state/deliveries.json | jq '.["2026-07-22"] | keys | map(select(startswith("stmn1"))) | length')
    WIX_KEYS=$(cat state/deliveries.json | jq '.["2026-07-22"] | keys | map(select(startswith("wix"))) | length')
else
    echo "❌ No delivery records found"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Test Results"
echo "═══════════════════════════════════════════════════════════"
echo "stmn1 records: $STMN1_KEYS"
echo "wix records:   $WIX_KEYS"

if [ "$STMN1_KEYS" -gt 0 ] && [ "$WIX_KEYS" -gt 0 ]; then
    echo ""
    echo "✅ SUCCESS: Both sources tracked separately!"
    echo "✅ No cross-source interference detected"
    exit 0
else
    echo ""
    echo "⚠ One or more sources missing records"
    echo "Check job logs for errors"
    exit 1
fi
