"""Safe Phase 1–4 -> Phase 5+6 upgrade. Run from backend.

python -m app.scripts.upgrade_phase56
Uses the Phase 2 upgrader for a timestamped SQLite DB backup and migration to head.
"""
from app.scripts.upgrade_phase2 import main as upgrade

if __name__ == '__main__':
    upgrade()
    print('Phase 5 and 6 tables installed. Existing investors, sessions and data preserved.')
