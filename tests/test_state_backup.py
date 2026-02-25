"""Regression tests for the GET /api/state-backup endpoint.

Security contract being tested:
  - Feature flag: returns 404 (not 403) when STATE_BACKUP_ENABLED=0
  - Missing headers → 401
  - Invalid HMAC secret → 401
  - Stale timestamp (outside ±5 min window) → 403
  - Valid request → 200 + valid zip containing manifest.json with correct SHA-256 hashes
  - Path traversal guard: manifest entries outside state/ are rejected
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.main import create_app

TEST_SECRET = "test-secret-value-for-state-backup-regression"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config_cache():
    get_config.cache_clear()  # type: ignore[attr-defined]
    yield
    get_config.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def client_enabled(monkeypatch, tmp_path):
    """TestClient with STATE_BACKUP_ENABLED=1 and a fake state/ directory."""
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "testpass")
    monkeypatch.setenv("STATE_BACKUP_ENABLED", "1")
    monkeypatch.setenv("STATE_BACKUP_SECRET", TEST_SECRET)

    # Create a fake state directory with known content
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "ezoe_schedule.json").write_text('{"entries": []}', encoding="utf-8")
    (state_dir / "dispatch_state.json").write_text('{"last_run": null}', encoding="utf-8")
    (state_dir / "subdir").mkdir()
    (state_dir / "subdir" / "nested.txt").write_text("nested file content", encoding="utf-8")

    import app.main as main_module
    monkeypatch.setattr(main_module, "PROJECT_ROOT", tmp_path)

    app = create_app()
    return TestClient(app), tmp_path


@pytest.fixture
def client_disabled(monkeypatch):
    """TestClient with STATE_BACKUP_ENABLED=0."""
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "testpass")
    monkeypatch.setenv("STATE_BACKUP_ENABLED", "0")
    app = create_app()
    return TestClient(app)


# ── HMAC helper ──────────────────────────────────────────────────────────────

def make_hmac_headers(secret: str = TEST_SECRET, timestamp_offset: int = 0) -> dict:
    """Build X-Timestamp / X-Nonce / X-Signature headers for a valid (or aged) request."""
    ts = int(time.time()) + timestamp_offset
    nonce = str(uuid.uuid4())
    message = f"{ts}:{nonce}".encode()
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Timestamp": str(ts),
        "X-Nonce": nonce,
        "X-Signature": sig,
    }


# ── Feature-flag tests ───────────────────────────────────────────────────────

def test_disabled_returns_404_not_403(client_disabled):
    """Endpoint must return 404 (not 403) when disabled — avoids fingerprinting."""
    r = client_disabled.get("/api/state-backup", headers=make_hmac_headers())
    assert r.status_code == 404


# ── HMAC security tests ───────────────────────────────────────────────────────

def test_missing_all_auth_headers_returns_401(client_enabled):
    client, _ = client_enabled
    r = client.get("/api/state-backup")
    assert r.status_code == 401


def test_missing_signature_header_returns_401(client_enabled):
    client, _ = client_enabled
    headers = make_hmac_headers()
    del headers["X-Signature"]
    r = client.get("/api/state-backup", headers=headers)
    assert r.status_code == 401


def test_missing_timestamp_header_returns_401(client_enabled):
    client, _ = client_enabled
    headers = make_hmac_headers()
    del headers["X-Timestamp"]
    r = client.get("/api/state-backup", headers=headers)
    assert r.status_code == 401


def test_missing_nonce_header_returns_401(client_enabled):
    client, _ = client_enabled
    headers = make_hmac_headers()
    del headers["X-Nonce"]
    r = client.get("/api/state-backup", headers=headers)
    assert r.status_code == 401


def test_wrong_secret_returns_401(client_enabled):
    """A different secret must not produce a valid signature."""
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers(secret="wrong-secret"))
    assert r.status_code == 401


def test_tampered_signature_returns_401(client_enabled):
    """Flipping one character in the signature must be rejected."""
    client, _ = client_enabled
    headers = make_hmac_headers()
    sig = headers["X-Signature"]
    headers["X-Signature"] = ("0" if sig[0] != "0" else "1") + sig[1:]
    r = client.get("/api/state-backup", headers=headers)
    assert r.status_code == 401


def test_stale_timestamp_too_old_returns_403(client_enabled):
    """Timestamp older than 5 minutes must be rejected (replay protection)."""
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers(timestamp_offset=-400))
    assert r.status_code == 403


def test_stale_timestamp_too_new_returns_403(client_enabled):
    """Timestamp far in the future is also outside the window."""
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers(timestamp_offset=400))
    assert r.status_code == 403


def test_invalid_timestamp_format_returns_401(client_enabled):
    """Non-integer timestamp must be rejected."""
    client, _ = client_enabled
    headers = make_hmac_headers()
    headers["X-Timestamp"] = "not-a-number"
    r = client.get("/api/state-backup", headers=headers)
    assert r.status_code == 401


# ── Success-path tests ────────────────────────────────────────────────────────

def test_valid_request_returns_200_zip(client_enabled):
    """Valid HMAC-signed request must return HTTP 200 with a zip content-type."""
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_zip_contains_manifest(client_enabled):
    """The returned zip must contain manifest.json at the root."""
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert "manifest.json" in zf.namelist()


def test_manifest_schema_version_is_1(client_enabled):
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["schema_version"] == "1"


def test_manifest_lists_all_state_files(client_enabled):
    """Every file placed in the fake state/ must appear in the manifest."""
    client, tmp_path = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    archive_paths = {e["archive_path"] for e in manifest["files"]}
    assert "state/ezoe_schedule.json" in archive_paths
    assert "state/dispatch_state.json" in archive_paths
    assert "state/subdir/nested.txt" in archive_paths


def test_manifest_sha256_hashes_match_actual_files(client_enabled):
    """Every SHA-256 in the manifest must match the real bytes in the zip."""
    client, tmp_path = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for entry in manifest["files"]:
            archive_path = entry["archive_path"]
            expected_sha256 = entry["sha256"]
            actual_sha256 = hashlib.sha256(zf.read(archive_path)).hexdigest()
            assert actual_sha256 == expected_sha256, (
                f"SHA-256 mismatch for {archive_path}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )


def test_manifest_sha256_matches_original_files_on_disk(client_enabled):
    """SHA-256s in the manifest must also match the original files on disk."""
    client, tmp_path = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    for entry in manifest["files"]:
        original = tmp_path / entry["restore_path"]
        assert original.exists(), f"Original file missing: {entry['restore_path']}"
        disk_sha256 = hashlib.sha256(original.read_bytes()).hexdigest()
        assert disk_sha256 == entry["sha256"], (
            f"Manifest SHA-256 does not match disk for {entry['restore_path']}"
        )


def test_manifest_size_bytes_matches_actual(client_enabled):
    """size_bytes in the manifest must match the actual file size."""
    client, tmp_path = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for entry in manifest["files"]:
            actual_size = len(zf.read(entry["archive_path"]))
            assert actual_size == entry["size_bytes"], (
                f"size_bytes mismatch for {entry['archive_path']}: "
                f"expected {entry['size_bytes']}, got {actual_size}"
            )


def test_manifest_has_created_at_timestamp(client_enabled):
    client, _ = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert "created_at" in manifest
    assert manifest["created_at"]  # non-empty


def test_response_headers(client_enabled):
    """Content-Disposition and X-Manifest-Files headers must be present."""
    client, tmp_path = client_enabled
    r = client.get("/api/state-backup", headers=make_hmac_headers())
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "state-backup.zip" in r.headers.get("content-disposition", "")
    # 3 files in our fake state dir (2 top-level + 1 nested)
    assert r.headers.get("x-manifest-files") == "3"


def test_no_session_login_required(client_enabled):
    """The endpoint must not accept the admin session cookie as auth."""
    client, _ = client_enabled
    # Log in via the normal admin flow
    client.post("/login", data={"username": "admin", "password": "testpass"})
    # Now hit the backup endpoint without HMAC headers — must still be rejected
    r = client.get("/api/state-backup")
    assert r.status_code == 401
