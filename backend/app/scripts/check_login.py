"""Read-only installation check; never creates accounts or changes passwords."""
from pathlib import Path
from contextlib import closing
import sqlite3
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.core.security import verify_password


def main():
    url=make_url(settings.database_url)
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:' or url.host:
        raise SystemExit('Unsupported database configuration. A local SQLite file is required.')
    path=Path(url.database).resolve()
    print('Project backend:',Path.cwd())
    print('Configured database:',path)
    if not path.is_file():
        print('DATABASE MISSING: run setup from the same extracted project folder.');return
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        integrity=db.execute('PRAGMA quick_check').fetchone()[0]
        print('Database check:',integrity)
        try:
            user=db.execute("SELECT is_active,role,password_hash FROM users WHERE email=?",('advisor@advicue.local',)).fetchone()
        except sqlite3.OperationalError:
            print('ACCOUNT TABLE MISSING: setup or migration did not complete.');return
        print('Supplied advisor account exists:',bool(user))
        if user:
            print('Account active:',bool(user[0]))
            print('Account role:',user[1])
            print('Password matches supplied sample:',verify_password(user[2],'Advisor2026!'))
        else:
            print('The supplied advisor account is missing from this database. Existing records have not been changed.')
    print('If these checks pass, restart the PC and launch RUN_WINDOWS.bat from this same folder.')
    print('Open http://127.0.0.1:8000 and type the credentials manually; avoid saved autofill.')

if __name__=='__main__':main()
