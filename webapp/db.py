"""SQLAlchemy engine and session setup (synchronous, like the rest of the app)"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from webapp.config import DATABASE_URL

connect_args = {}
engine_kwargs = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite'):
    connect_args['check_same_thread'] = False
    db_file = DATABASE_URL.split('///', 1)[-1]
    if db_file and db_file != ':memory:':
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
else:
    engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """Create any missing tables and columns. Idempotent.

    Plain create_all (plus additive micro-migrations below) is enough while
    the schema is young; switch to Alembic migrations once the schema needs
    anything beyond ADD COLUMN.
    """
    import webapp.models  # noqa: F401  -- register models on Base
    Base.metadata.create_all(engine)
    _migrate()


def _migrate():
    """Additive micro-migrations: create_all never alters existing tables,
    so columns added to models after a table shipped are added here."""
    from sqlalchemy import inspect, text

    blob_type = 'BYTEA' if engine.dialect.name == 'postgresql' else 'BLOB'
    added = {
        'body_profiles': {'skin_color': 'VARCHAR'},
        # DEFAULT backfills existing rows: pre-existing designs are outfits
        'designs': {'kind': "VARCHAR DEFAULT 'outfit' NOT NULL",
                    'preview': 'TEXT',
                    'drape_glb': blob_type,
                    'fabric_color': 'VARCHAR'},
        'users': {'units': "VARCHAR DEFAULT 'in' NOT NULL"},
    }
    inspector = inspect(engine)
    for table, columns in added.items():
        existing = {c['name'] for c in inspector.get_columns(table)}
        for column, ddl_type in columns.items():
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
