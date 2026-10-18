from pathlib import Path
import hashlib,io,sqlite3,zipfile
import pytest
from app.scripts import prepare_sample_database as setup


def sample(tmp_path,monkeypatch):
    p=tmp_path/'source.db'
    with sqlite3.connect(p) as db:
        db.executescript("CREATE TABLE users(email TEXT,is_active INTEGER); INSERT INTO users VALUES('advisor@advicue.local',1); CREATE TABLE login_sessions(id TEXT);")
    payload=p.read_bytes();monkeypatch.setattr(setup,'SAMPLE_SHA256',hashlib.sha256(payload).hexdigest())
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr(setup.SAMPLE_MEMBER,payload)
    return out.getvalue(),payload


def test_fresh_database_receives_sample_account(tmp_path,monkeypatch):
    archive,payload=sample(tmp_path,monkeypatch);target=tmp_path/'fresh.db'
    assert setup.prepare(target,lambda:archive)=='SAMPLE_ACCOUNT_READY'
    assert target.read_bytes()==payload


def test_existing_empty_schema_is_backed_up_before_initialization(tmp_path,monkeypatch):
    archive,payload=sample(tmp_path,monkeypatch);target=tmp_path/'fresh.db'
    with sqlite3.connect(target) as db:db.executescript("CREATE TABLE users(email TEXT,is_active INTEGER); CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('0014_advisor_identity');")
    db.close()
    assert setup.prepare(target,lambda:archive)=='SAMPLE_ACCOUNT_READY'
    with sqlite3.connect(target.with_name('fresh_BEFORE_SAMPLE_SETUP.db')) as backup:
        assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert backup.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0014_advisor_identity'
        assert backup.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0


def test_any_existing_data_and_passwords_are_preserved_without_download(tmp_path):
    target=tmp_path/'populated.db'
    with sqlite3.connect(target) as db:db.executescript("CREATE TABLE users(email TEXT,password_hash TEXT); INSERT INTO users VALUES('existing@example.local','do-not-reset');")
    before=target.read_bytes()
    def forbidden():raise AssertionError('Existing database must not trigger a download')
    assert setup.prepare(target,forbidden)=='EXISTING_RECORDS_PRESERVED'
    assert target.read_bytes()==before


def test_unrelated_database_with_records_is_preserved(tmp_path):
    target=tmp_path/'custom.db'
    with sqlite3.connect(target) as db:db.executescript('CREATE TABLE investments(amount INTEGER); INSERT INTO investments VALUES(500);')
    assert setup.prepare(target,lambda:None)=='EXISTING_RECORDS_PRESERVED'


def test_fingerprint_mismatch_cannot_replace_database(tmp_path,monkeypatch):
    archive,_=sample(tmp_path,monkeypatch);target=tmp_path/'fresh.db'
    with sqlite3.connect(target) as db:db.execute('CREATE TABLE users(email TEXT)')
    before=target.read_bytes();monkeypatch.setattr(setup,'SAMPLE_SHA256','0'*64)
    with pytest.raises(ValueError,match='fingerprint'):setup.prepare(target,lambda:archive)
    assert target.read_bytes()==before


def test_failed_download_does_not_create_a_database(tmp_path):
    def failed():raise OSError('Network unavailable')
    target=tmp_path/'fresh.db'
    with pytest.raises(OSError):setup.prepare(target,failed)
    assert not target.exists()


def test_database_populated_during_download_is_not_replaced(tmp_path,monkeypatch):
    archive,_=sample(tmp_path,monkeypatch);target=tmp_path/'fresh.db'
    def fetch():
        with sqlite3.connect(target) as db:db.executescript("CREATE TABLE users(email TEXT); INSERT INTO users VALUES('new@example.local');")
        db.close()
        return archive
    assert setup.prepare(target,fetch)=='EXISTING_RECORDS_PRESERVED'
    with sqlite3.connect(target) as db:assert db.execute('SELECT email FROM users').fetchone()[0]=='new@example.local'


def test_running_launcher_never_downloads_sample_database():
    root=Path(__file__).resolve().parents[2]
    start=(root/'scripts/START_WINDOWS.ps1').read_text(encoding='utf-8')
    connected=(root/'scripts/PREPARE_FIRST_RUN.ps1').read_text(encoding='utf-8')
    assert 'prepare_sample_database' not in start
    assert '-m app.scripts.prepare_sample_database --download' in connected
