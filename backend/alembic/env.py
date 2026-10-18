from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 - loads mapped classes

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            # SQLite cannot batch-recreate a referenced table while FK enforcement is ON.
            # SETUP_WINDOWS.ps1 already makes a SQLite backup before migration;
            # re-enable FKs and check integrity immediately after migrations.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        # SQLite DDL is non-transactional; explicitly persist Alembic version bookkeeping.
        connection.commit()
        if connection.dialect.name == "sqlite":
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if violations:
                raise RuntimeError(f"SQLite foreign-key integrity failed after migration: {violations[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
