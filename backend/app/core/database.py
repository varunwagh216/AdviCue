from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from sqlalchemy.engine import make_url

_url=make_url(settings.database_url)
if _url.get_backend_name()!='sqlite' or _url.host or (_url.database or '').startswith(('//','\\\\')):
    raise RuntimeError('AdviCue requires a SQLite database on this computer.')


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_recycle=1800,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
