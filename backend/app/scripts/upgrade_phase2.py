"""Safe local SQLite upgrader for Phase 1 -> Phase 2 (including blank version workaround).

Usage from backend/: python -m app.scripts.upgrade_phase2
Always makes a timestamped backup of an existing SQLite database before modifying it.
"""
from __future__ import annotations
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.core.config import settings


def main():
    url=settings.database_url
    if not url.startswith('sqlite:///'):
        raise SystemExit('This safe upgrader supports local SQLite only. Use normal alembic for other databases.')
    path=Path(url.removeprefix('sqlite:///')).resolve()
    if not path.exists():
        print('No existing local database; running initial migrations.')
        command.upgrade(Config('alembic.ini'),'head')
        print('Ready: Phase 2 schema installed.')
        return
    backup=path.with_name(path.name+'.backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(path,backup)
    print('Created backup:',backup)
    with sqlite3.connect(path) as connection:
        tables={x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version=connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] if 'alembic_version' in tables and connection.execute('SELECT COUNT(*) FROM alembic_version').fetchone()[0] else None
        phase1={'organizations','users','login_sessions','investors','audit_events'}
        if version is None and tables.intersection(phase1):
            if not phase1.issubset(tables):
                raise SystemExit('Unknown/incomplete legacy schema. No migration performed; backup retained.')
            cols={x[1] for x in connection.execute('PRAGMA table_info(users)')}
            if 'external_advisor_code' in cols:
                raise SystemExit('Phase 2 columns exist without a revision marker. Stop and investigate; backup retained.')
            print('Detected Phase 1 database without recorded Alembic revision; repairing migration marker.')
    config=Config('alembic.ini')
    if version is None and tables.intersection(phase1):
        command.stamp(config,'0001_phase1')
    command.upgrade(config,'head')
    print('Ready: Phase 2 schema installed. Original account records preserved.')

if __name__=='__main__':
    main()
