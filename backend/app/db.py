from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config
from app.models import Base

_kwargs = {}
if config.DATABASE_URL.startswith("sqlite"):
    # FastAPI handles requests on several threads; SQLite needs this flag for that.
    _kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Azure SQL (serverless) can pause itself; pre-ping re-opens dropped connections.
    _kwargs["pool_pre_ping"] = True

engine = create_engine(config.DATABASE_URL, **_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
