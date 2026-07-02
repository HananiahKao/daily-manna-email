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

# Start dev server on 0.0.0.0 (accessible via VPN from outside local network)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
