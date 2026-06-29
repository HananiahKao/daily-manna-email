#!/bin/bash
# Start FastAPI dev server with .env sourced
# Usage: ./scripts/dev-server.sh

set -e

# Source .env if it exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Start dev server
python -m uvicorn app.main:app --reload --port 8000
