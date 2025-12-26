#!/usr/bin/env python3
"""
Generate OAuth encryption key for token encryption.

This script generates a secure 32-byte encryption key and outputs it in the format
required for the OAUTH_ENCRYPTION_KEY environment variable.

Usage:
    python scripts/generate_oauth_key.py

Output:
    A base64-encoded 32-byte key suitable for OAUTH_ENCRYPTION_KEY
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.token_encryption import generate_encryption_key

if __name__ == "__main__":
    key = generate_encryption_key()
    print("Generated OAuth encryption key:")
    print(key)
    print()
    print("Add this to your environment variables as OAUTH_ENCRYPTION_KEY:")
    print(f"export OAUTH_ENCRYPTION_KEY={key}")
    print()
    print("For Render deployment, add it as an environment variable in the dashboard.")
