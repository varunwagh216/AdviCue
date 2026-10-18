"""Safe Phase 1–6 -> Phase 7–8 migration with timestamped SQLite backup.
Run from the backend directory: python -m app.scripts.upgrade_phase78
"""
from app.scripts.upgrade_phase2 import main

if __name__ == '__main__':
    main()
    print('Phase 7–8 local AI and meeting-note tables installed.')
