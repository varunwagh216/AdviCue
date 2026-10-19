"""Explicit connected setup for fresh source downloads. Never called at runtime."""
from pathlib import Path
from contextlib import closing
import argparse
import hashlib
import io
import os
import sqlite3
import tempfile
import urllib.request
import zipfile

SAMPLE_URL='https://github.com/varunwagh216/AdviCue/releases/download/submission/AdviCue_AI.zip'
SAMPLE_MEMBER='AdviCue_AI/backend/advicue.db'
SAMPLE_SHA256='2ce2c373918931e709b881c6a60773f11e270e7abcb3583f51e6eb8682af5480'


def has_records(path:Path)->bool:
    if not path.exists() or path.stat().st_size==0:return False
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='alembic_version'")]
        # Preserve any existing data, even if the database is not this app's schema.
        for name in tables:
            escaped=name.replace('"','""')
            if db.execute(f'SELECT 1 FROM "{escaped}" LIMIT 1').fetchone():return True
    return False


def fetch_archive()->bytes:
    bundled=Path(__file__).resolve().parents[2]/'sample-data'/'advicue.sqlite3'
    if not bundled.is_file():raise ValueError('Bundled sample database missing. Extract the complete latest project ZIP.')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr(SAMPLE_MEMBER,bundled.read_bytes())
    return out.getvalue()



def prepare(path:Path,fetch=fetch_archive)->str:
    path=path.resolve()
    if has_records(path):return 'EXISTING_RECORDS_PRESERVED'
    with zipfile.ZipFile(io.BytesIO(fetch())) as archive:
        member=archive.getinfo(SAMPLE_MEMBER)
        if member.file_size>8*1024*1024:raise ValueError('Sample database exceeds the size limit')
        payload=archive.read(member)
    if hashlib.sha256(payload).hexdigest()!=SAMPLE_SHA256:
        raise ValueError('Sample database fingerprint mismatch; existing database was not changed')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='advicue-prepared-',suffix='.db',dir=path.parent)
    pending=Path(name)
    try:
        with os.fdopen(fd,'wb') as file:file.write(payload)
        with closing(sqlite3.connect(pending)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Sample database integrity check failed')
            if db.execute('SELECT COUNT(*) FROM login_sessions').fetchone()[0]:raise ValueError('Sample database unexpectedly contains sessions')
            if not db.execute("SELECT 1 FROM users WHERE email='advisor@advicue.local' AND is_active=1").fetchone():raise ValueError('Sample advisor account is missing')
        # Recheck after download so data added in the meantime cannot be replaced.
        if has_records(path):return 'EXISTING_RECORDS_PRESERVED'
        if path.with_name(path.name+'-wal').exists() or path.with_name(path.name+'-shm').exists():
            raise ValueError('SQLite is using WAL files. Stop the backend and checkpoint the database before sample setup')
        if path.exists() and path.stat().st_size:
            backup=path.with_name(path.stem+'_BEFORE_SAMPLE_SETUP'+path.suffix)
            if not backup.exists():
                with closing(sqlite3.connect(path)) as old,closing(sqlite3.connect(backup)) as dest:old.backup(dest)
        pending.replace(path)
        return 'SAMPLE_ACCOUNT_READY'
    finally:
        if pending.exists():pending.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true',required=True,help='Allow the explicit setup download')
    parser.parse_args()
    from app.core.config import settings
    from sqlalchemy.engine import make_url
    url=make_url(settings.database_url)
    if url.get_backend_name()!='sqlite' or url.host or url.query or not url.database or url.database==':memory:' or url.database.startswith(('//','\\\\')):
        raise SystemExit('Sample setup requires a local SQLite file')
    try:status=prepare(Path(url.database))
    except Exception as exc:raise SystemExit(f'Sample setup failed: {exc}. Existing records were preserved. Stop the backend before retrying.') from exc
    if status=='SAMPLE_ACCOUNT_READY':print('Sample advisor account ready: advisor@advicue.local / Advisor2026!')
    else:print('Existing records and passwords preserved. Use the account already registered in this database.')


if __name__=='__main__':main()
