"""Shared test setup: a fresh app with its own session store and a fake clock."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Let tests import `main` and `app` from the backend folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dependencies import get_session_service  # noqa: E402
from app.services.session_service import SessionService  # noqa: E402
from main import create_app  # noqa: E402


class FakeClock:
    """A clock tests can move forward, to check session expiry without waiting."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += timedelta(minutes=minutes)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(clock: FakeClock) -> SessionService:
    return SessionService(ttl_minutes=30, max_messages=40, clock=clock)


@pytest.fixture
def client(service: SessionService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)
