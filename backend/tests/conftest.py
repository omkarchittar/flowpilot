import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from flowpilot.app import create_app
from flowpilot.auth import get_db
from flowpilot.config import Settings
from flowpilot.models import User
from flowpilot.security import hash_password

PASSWORD = "correct-long-password"


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def api(db):
    user = User(
        email="member@example.com",
        name="Member",
        password_hash=hash_password(PASSWORD),
        role="requester",
    )
    admin = User(
        email="admin@example.com", name="Admin", password_hash=hash_password(PASSWORD), role="admin"
    )
    db.add_all([user, admin])
    db.flush()
    app = create_app(Settings())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, user, admin
