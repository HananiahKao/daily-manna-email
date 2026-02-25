#!/usr/bin/env bash
# scripts/build.sh — Render.com build script
#
# Replaces the direct `pip install -r requirements.txt` build command.
# After installing dependencies, optionally restores the state/ directory
# from the currently running production server before the new instance starts.
#
# Required env vars for state restore:
#   STATE_RESTORE_ENABLED=1        — must be set to trigger the restore
#   STATE_SOURCE_URL               — base URL of the currently running instance to pull state from
#   STATE_BACKUP_SECRET            — shared HMAC secret (same value on server)
#
# Optional:
#   STATE_BACKUP_TIMEOUT           — curl timeout in seconds (default: 60)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

# Load .env if present (development / local builds)
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

# ── 1. Install Python dependencies ──────────────────────────────────────────
echo "[build] Installing Python dependencies..."
pip install -r "$ROOT/requirements.txt"
echo "[build] Dependencies installed."

# ── 2. State restore ────────────────────────────────────────────────────────
RESTORE_ENABLED="${STATE_RESTORE_ENABLED:-0}"

if [[ "$RESTORE_ENABLED" != "1" && "$RESTORE_ENABLED" != "true" && \
      "$RESTORE_ENABLED" != "on"  && "$RESTORE_ENABLED" != "yes" ]]; then
  echo "[build] STATE_RESTORE_ENABLED is not set or disabled — skipping state restore."
  exit 0
fi

STATE_SOURCE_URL="${STATE_SOURCE_URL:-}"
if [[ -z "$STATE_SOURCE_URL" ]]; then
  echo "[build] WARNING: STATE_RESTORE_ENABLED=1 but STATE_SOURCE_URL is not set — skipping restore."
  exit 0
fi

STATE_BACKUP_SECRET="${STATE_BACKUP_SECRET:-}"
if [[ -z "$STATE_BACKUP_SECRET" ]]; then
  echo "[build] WARNING: STATE_BACKUP_SECRET is not set — skipping restore."
  exit 0
fi

TIMEOUT="${STATE_BACKUP_TIMEOUT:-60}"
ENDPOINT="${STATE_SOURCE_URL%/}/api/state-backup"

echo "[build] Fetching state backup from: $ENDPOINT"

# Compute HMAC-SHA256 signature (Python stdlib only — no extra deps needed)
TIMESTAMP=$(date +%s)
NONCE=$("$PYTHON_BIN" -c "import uuid; print(str(uuid.uuid4()))")
SIGNATURE=$("$PYTHON_BIN" - <<PYEOF
import hashlib, hmac as _hmac
secret = "${STATE_BACKUP_SECRET}"
message = "${TIMESTAMP}:${NONCE}"
sig = _hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
print(sig)
PYEOF
)

BACKUP_ZIP="$ROOT/state-backup-$TIMESTAMP.zip"

# Download — non-fatal: any failure logs a warning and the build continues
HTTP_STATUS=$(
  curl \
    --silent \
    --show-error \
    --max-time "$TIMEOUT" \
    --output "$BACKUP_ZIP" \
    --write-out "%{http_code}" \
    -H "X-Timestamp: $TIMESTAMP" \
    -H "X-Nonce: $NONCE" \
    -H "X-Signature: $SIGNATURE" \
    "$ENDPOINT"
) || {
  echo "[build] WARNING: curl failed — skipping state restore. Deploy will continue with empty state."
  rm -f "$BACKUP_ZIP"
  exit 0
}

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "[build] WARNING: Backup endpoint returned HTTP $HTTP_STATUS — skipping state restore."
  rm -f "$BACKUP_ZIP"
  exit 0
fi

if [[ ! -s "$BACKUP_ZIP" ]]; then
  echo "[build] WARNING: Downloaded zip is empty — skipping state restore."
  rm -f "$BACKUP_ZIP"
  exit 0
fi

echo "[build] Backup downloaded (HTTP $HTTP_STATUS). Validating and extracting..."

# Validate SHA-256 hashes for all files, then extract.
# Path traversal guard: only paths starting with "state/" are permitted.
"$PYTHON_BIN" - <<PYEOF
import hashlib, json, os, sys, zipfile
from pathlib import Path

ROOT = Path("${ROOT}")
zip_path = Path("${BACKUP_ZIP}")

try:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            print("[build] ERROR: manifest.json missing from archive.")
            sys.exit(1)

        manifest = json.loads(zf.read("manifest.json"))

        if manifest.get("schema_version") != "1":
            print(f"[build] ERROR: Unknown manifest schema_version: {manifest.get('schema_version')!r}")
            sys.exit(1)

        print(f"[build] Manifest created_at:  {manifest.get('created_at')}")
        print(f"[build] Server version:        {manifest.get('server_version')}")
        print(f"[build] Files in backup:       {len(manifest.get('files', []))}")

        # Validate all SHA-256 hashes before writing anything (all-or-nothing)
        for entry in manifest.get("files", []):
            archive_path = entry["archive_path"]
            if archive_path == "manifest.json":
                continue
            if archive_path not in names:
                print(f"[build] ERROR: {archive_path!r} in manifest but missing from zip.")
                sys.exit(1)
            actual = hashlib.sha256(zf.read(archive_path)).hexdigest()
            if actual != entry["sha256"]:
                print(f"[build] ERROR: SHA-256 mismatch for {archive_path!r}")
                print(f"         expected: {entry['sha256']}")
                print(f"         got:      {actual}")
                sys.exit(1)

        print("[build] All SHA-256 hashes verified. Extracting...")

        for entry in manifest.get("files", []):
            archive_path = entry["archive_path"]
            restore_path = entry["restore_path"]
            if archive_path == "manifest.json":
                continue

            # Path traversal guard
            norm = os.path.normpath(restore_path)
            if norm.startswith("..") or not norm.startswith("state"):
                print(f"[build] WARNING: Skipping {restore_path!r} — unsafe path, ignoring.")
                continue

            dest = ROOT / norm
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(archive_path))
            print(f"[build]   Restored: {restore_path} ({entry['size_bytes']} bytes)")

        print("[build] State restore complete.")

except zipfile.BadZipFile:
    print("[build] ERROR: Downloaded file is not a valid zip archive.")
    sys.exit(1)
except Exception as exc:
    print(f"[build] ERROR: {exc}")
    sys.exit(1)
PYEOF

RESTORE_EXIT=$?
rm -f "$BACKUP_ZIP"

if [[ $RESTORE_EXIT -ne 0 ]]; then
  echo "[build] WARNING: State restore failed. Deploy will continue with empty state."
fi

echo "[build] Build complete."
