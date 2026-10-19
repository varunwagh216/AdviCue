from types import SimpleNamespace
import sqlite3
from app.scripts import check_login


def test_check_preserves_database(tmp_path, monkeypatch, capsys):
    from app.core.security import hash_password
    path = tmp_path / 'book.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE users(email TEXT,is_active INTEGER,role TEXT,password_hash TEXT)')
    db.execute('INSERT INTO users VALUES(?,?,?,?)', ('advisor@advicue.local', 1, 'ADVISOR', hash_password('Advisor2026!')))
    db.commit()
    db.close()
    before = path.read_bytes()
    monkeypatch.setattr(check_login, 'settings', SimpleNamespace(database_url='sqlite:///' + path.as_posix()))
    check_login.main()
    assert 'Password matches supplied sample: True' in capsys.readouterr().out
    assert path.read_bytes() == before


def test_missing_database_is_not_created(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'missing.db'
    monkeypatch.setattr(check_login, 'settings', SimpleNamespace(database_url='sqlite:///' + path.as_posix()))
    check_login.main()
    assert 'DATABASE MISSING' in capsys.readouterr().out
    assert not path.exists()


def test_missing_account_is_not_created(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'empty.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE users(email TEXT,is_active INTEGER,role TEXT,password_hash TEXT)')
    db.commit()
    db.close()
    before = path.read_bytes()
    monkeypatch.setattr(check_login, 'settings', SimpleNamespace(database_url='sqlite:///' + path.as_posix()))
    check_login.main()
    assert 'Supplied advisor account exists: False' in capsys.readouterr().out
    assert path.read_bytes() == before
