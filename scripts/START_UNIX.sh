#!/usr/bin/env bash
# Requires preinstalled dependencies, built React assets, local binaries and models.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
[[ -x .venv/bin/python ]] || { echo 'Prepare a local Python environment first.'; exit 1; }
export FRONTEND_ORIGIN=http://127.0.0.1:8000 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
.venv/bin/python -m app.scripts.prepare_whisper --check
# Start your locally installed llama-server on 127.0.0.1:8080 before this script.
.venv/bin/python -m app.scripts.backup_sqlite_before_upgrade
.venv/bin/python -m alembic upgrade head
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
