from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

_TEST_DB_URL = "sqlite:///./test.db"
_engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def no_link_checks():
    """Ingestion checks edition links over the network; tests treat every link as working unless they say otherwise."""
    with patch("app.scheduler.check_links", side_effect=lambda urls: {url: True for url in urls}) as check:
        yield check


@pytest.fixture(autouse=True)
def no_genre_model():
    """The genre model runs on Ollama; tests answer for it (None: it can't be reached) unless they say otherwise."""
    with patch("app.ingestion.genre_filter.ask_model", return_value=None) as ask:
        yield ask


@pytest.fixture
def db():
    session = _TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
