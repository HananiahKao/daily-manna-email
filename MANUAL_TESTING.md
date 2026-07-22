# Manual Testing Guide: Real Gmail Integration

This guide explains how to test the delivery tracking system with **real Gmail API** (not mocked).

## Prerequisites

- ✅ OAuth credentials configured (client_secret.json in place)
- ✅ `.env` file with `SMTP_USER` and `EMAIL_TO` set
- ✅ Python virtual environment activated

## Step 1: Start the FastAPI Server

The server handles OAuth authentication. Start it locally:

```bash
# From repo root (sources .env automatically)
./scripts/dev-server.sh
```

The server will start at `http://localhost:8000`.

## Step 2: Authenticate via OAuth

1. Open your browser to `http://localhost:8000`
2. Navigate to the auth endpoint (or let the app prompt)
3. Click "Login with Google"
4. Grant permissions to access your Gmail account
5. The token is encrypted and stored in `.env.local`

The system will use this token for real Gmail API calls going forward.

## Step 3: Run the Delivery Tracker Test

Once authenticated, you can test delivery tracking with real Gmail:

```bash
# Set up test email recipients
export EMAIL_TO="your-test-email@gmail.com"
export DEBUG_MODE=1  # Sends to EMAIL_FROM (your account)

# Run the core send function with real Gmail
python -c "
import sjzl_daily_email as sjzl
result = sjzl.send_email('Test Subject', 'Test Body')
print('Sent to:', result)
print('Message IDs recorded:', result)
"
```

## Step 4: Verify Delivery Tracking

Check that deliveries were recorded:

```bash
python -c "
import json
from pathlib import Path

deliveries_file = Path('state/deliveries.json')
if deliveries_file.exists():
    data = json.loads(deliveries_file.read_text())
    print('Deliveries recorded:')
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print('No deliveries recorded yet')
"
```

Expected output:
```json
{
  "2026-06-29": {
    "your-test-email@gmail.com": {
      "message_id": "18c1234567890abcdef...",
      "sent_at": "2026-06-29T06:00:15.123456+08:00"
    }
  }
}
```

## Step 5: Test Idempotent Recovery

Run the send again without clearing deliveries — it should skip (no duplicate):

```bash
python -c "
import sjzl_daily_email as sjzl
result = sjzl.send_email('Test Subject', 'Test Body')
print('Result:', result)
print('Should be empty (already delivered today):', result == {})
"
```

## Step 6: Verify in Gmail

Check your Gmail account:
1. Open Gmail
2. Go to **Sent Mail**
3. Verify the test email was sent exactly once (idempotent recovery prevents duplicates)

## Cleanup

After testing:

```bash
# Clear delivery records to test again
rm -f state/deliveries.json

# Or clear just today's deliveries
python -c "
import json
from pathlib import Path
import datetime as dt

deliveries_file = Path('state/deliveries.json')
if deliveries_file.exists():
    data = json.loads(deliveries_file.read_text())
    today = dt.date.today().isoformat()
    if today in data:
        del data[today]
    deliveries_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
"
```

## Troubleshooting

**"Token expired" error:**
- The OAuth token may have expired. Run the server again and re-authenticate.

**"Gmail API not enabled":**
- Check that the OAuth app has Gmail API enabled in Google Cloud Console.

**No message_id in result:**
- Verify the Gmail service is authenticated (check `.env.local` for token).
- Check server logs for API errors.

## What This Tests

✅ Real Gmail OAuth authentication  
✅ Real message sending via Gmail API  
✅ Delivery record creation with actual message IDs  
✅ Idempotent filtering (no duplicates on retry)  
✅ Per-recipient tracking (each recipient tracked independently)  
✅ Per-date tracking (tomorrow's email is separate from today)  

## Automated Tests vs. Manual Testing

| Aspect | Unit Tests | Smoke Tests | Manual Test |
|--------|-----------|------------|-------------|
| Mocks Gmail | ✅ Yes | No | ❌ No (real) |
| Real file I/O | ❌ No | ✅ Yes | ✅ Yes |
| Real Gmail API | ❌ No | ❌ No | ✅ Yes |
| Speed | ⚡ Fast | ⚡ Fast | 🐢 Slow |
| Purpose | Logic | Reliability | Production |

All three are needed:
- **Unit tests** catch logic bugs (358 tests, <1s)
- **Smoke tests** catch file I/O issues (3 tests, <0.1s)
- **Manual test** catches real-world Gmail issues (5-10 min)
