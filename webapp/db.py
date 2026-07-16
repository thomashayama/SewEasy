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
    """Create any missing tables. Idempotent.

    Plain create_all is enough while the schema is young; switch to Alembic
    migrations once there is production data to preserve.
    """
    import webapp.models  # noqa: F401  -- register models on Base
    Base.metadata.create_all(engine)
