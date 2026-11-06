"""
Unit tests for app/database.py.

Nothing here needs Postgres: engines point at in-memory SQLite, and the
module is imported normally (no sys.modules tricks), so the shared `Base`
that conftest.py and the models use is never replaced mid-run.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app import database
from app.config import settings

SQLITE_URL = "sqlite://"


# get_engine

def test_get_engine_uses_the_url_it_is_given():
    engine = database.get_engine(SQLITE_URL)

    assert isinstance(engine, Engine)
    assert engine.url == make_url(SQLITE_URL)


def test_get_engine_defaults_to_configured_database():
    engine = database.get_engine()

    assert engine.url == make_url(settings.DATABASE_URL)


def test_get_engine_logs_and_reraises_failures(capsys):
    boom = SQLAlchemyError("cannot build engine")

    with patch("app.database.create_engine", side_effect=boom):
        with pytest.raises(SQLAlchemyError, match="cannot build engine"):
            database.get_engine(SQLITE_URL)

    assert "Error creating engine" in capsys.readouterr().out



# get_sessionmaker
def test_get_sessionmaker_returns_a_factory_bound_to_the_engine():
    engine = database.get_engine(SQLITE_URL)

    factory = database.get_sessionmaker(engine)

    assert isinstance(factory, sessionmaker)
    session = factory()
    try:
        assert isinstance(session, Session)
        assert session.get_bind() is engine
    finally:
        session.close()


def test_sessions_from_factory_do_not_autoflush():
    factory = database.get_sessionmaker(database.get_engine(SQLITE_URL))

    with factory() as session:
        assert session.autoflush is False


def test_sessions_from_factory_can_run_queries():
    factory = database.get_sessionmaker(database.get_engine(SQLITE_URL))

    with factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1

# Base
def test_base_exposes_metadata():
    assert isinstance(database.Base.metadata, MetaData)


def test_user_model_is_registered_on_the_shared_base():
    # Guards against the model defining its own declarative_base(), which
    # would make create_all/drop_all in conftest.py silently do nothing.
    from app.models.user import User

    assert User.metadata is database.Base.metadata
    assert "users" in database.Base.metadata.tables


# get_db dependency
def test_get_db_yields_a_session_then_closes_it():
    fake_session = MagicMock(spec=Session)

    with patch("app.database.SessionLocal", return_value=fake_session):
        dependency = database.get_db()

        assert next(dependency) is fake_session
        fake_session.close.assert_not_called()

        with pytest.raises(StopIteration):
            next(dependency)

    fake_session.close.assert_called_once()


def test_get_db_closes_session_when_the_request_fails():
    fake_session = MagicMock(spec=Session)

    with patch("app.database.SessionLocal", return_value=fake_session):
        dependency = database.get_db()
        next(dependency)

        with pytest.raises(RuntimeError, match="handler blew up"):
            dependency.throw(RuntimeError("handler blew up"))

    fake_session.close.assert_called_once()


def test_get_db_hands_out_a_fresh_session_each_time():
    sessions = [MagicMock(spec=Session), MagicMock(spec=Session)]

    with patch("app.database.SessionLocal", side_effect=sessions):
        first = next(database.get_db())
        second = next(database.get_db())

    assert first is not second