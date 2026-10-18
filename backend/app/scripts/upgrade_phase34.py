"""Safe, idempotent SQLite schema upgrade for Phase 1/2 -> 3+4.

Run from backend/: python -m app.scripts.upgrade_phase34
The existing tested upgrader backs up the DB, repairs a known Phase-1 version
marker issue when necessary, and migrates to the current Alembic head.
"""
from app.scripts.upgrade_phase2 import main as prior_upgrade


def main():
    prior_upgrade()
    print('Phase 3 and 4 migrations applied. Your existing database is preserved.')


if __name__ == '__main__':
    main()
