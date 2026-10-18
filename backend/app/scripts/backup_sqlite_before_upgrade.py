"""Create an atomic local SQLite snapshot before a schema migration.

No cloud files, and never delete/change the source database.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from urllib.parse import unquote
from app.core.config import settings

TARGET='0014_advisor_identity'

def main():
    url=settings.database_url
    if not url.startswith('sqlite:///'):
        print('SQLite backup helper skipped for other database engines.')
        return
    path=Path(unquote(url.removeprefix('sqlite:///'))).resolve()
    if not path.exists():
        print('Fresh database; no backup necessary.')
        return
    with sqlite3.connect(str(path)) as db:
        try:row=db.execute('select version_num from alembic_version limit 1').fetchone()
        except sqlite3.DatabaseError:row=None
        if row and row[0]==TARGET:
            print('SQLite already at migration; no backup necessary.')
            return
        target=path.with_name(path.stem+'_BACKUP_BEFORE_UPGRADE'+path.suffix)
        if target.exists():
            print('Existing pre-upgrade backup preserved:',target)
            return
        with sqlite3.connect(str(target)) as dest:db.backup(dest)
    print('Created safe SQLite backup:',target)

if __name__=='__main__':main()
