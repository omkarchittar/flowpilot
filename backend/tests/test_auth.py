from datetime import timedelta

import pytest
from sqlalchemy import select

from flowpilot.db import utcnow
from flowpilot.models import AuthSession, LoginThrottle
from flowpilot.security import session_digest

pytestmark = pytest.mark.postgres
PASSWORD = "correct-long-password"
ORIGIN = "http://localhost:3001"


def login(client, email="member@example.com"):
    return client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )


def test_login_sets_http_only_cookie_and_stores_only_hash(api, db):
    client, user, _ = api
    response = login(client)
    assert response.status_code == 200
    assert response.json()["user"]["id"] == user.id
    assert "password" not in response.text
    token = client.cookies.get("flowpilot_session")
    assert token and len(token) >= 40
    stored = db.get(AuthSession, session_digest(token))
    assert stored and stored.user_id == user.id
    assert stored.token_hash != token
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "access_token" not in response.json()


def test_me_logout_and_revoked_session(api):
    client, _, _ = api
    response = login(client)
    csrf = response.json()["csrf_token"]
    assert client.get("/api/auth/me").status_code == 200
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://attacker.example"}, {"Origin": ORIGIN, "X-CSRF-Token": "forged"}],
)
def test_cookie_mutations_require_csrf_and_allowed_origin(api, headers):
    client, _, _ = api
    login(client)
    assert client.post("/api/auth/logout", headers=headers).status_code == 403


def test_api_token_auth_does_not_require_browser_csrf(api):
    client, user, _ = api
    response = client.post("/api/auth/token", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert not client.cookies.get("flowpilot_session")
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/auth/me", headers=headers).json()["user"]["id"] == user.id
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_expired_session_and_disabled_user_fail_closed(api, db):
    client, user, _ = api
    login(client)
    stored = db.get(AuthSession, session_digest(client.cookies["flowpilot_session"]))
    stored.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/auth/me").status_code == 401
    login(client)
    user.active = False
    db.flush()
    assert client.get("/api/auth/me").status_code == 401


def test_failed_logins_are_persisted_and_throttled(api, db):
    client, _, _ = api
    for _ in range(10):
        response = client.post(
            "/api/auth/token", json={"email": "member@example.com", "password": "wrong"}
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/token", json={"email": "member@example.com", "password": PASSWORD}
    )
    assert response.status_code == 429
    assert len(db.scalars(select(LoginThrottle)).all()) == 2


def test_no_role_header_can_authorize_admin_action(api):
    client, _, _ = api
    auth = client.post(
        "/api/auth/token", json={"email": "member@example.com", "password": PASSWORD}
    ).json()
    response = client.post(
        "/api/admin/users",
        headers={"Authorization": "Bearer " + auth["access_token"], "X-Role": "admin"},
        json={"email": "new@example.com", "name": "New", "password": PASSWORD, "role": "admin"},
    )
    assert response.status_code == 403


def test_admin_creates_users_and_cannot_disable_last_admin(api):
    client, _, admin = api
    token = client.post(
        "/api/auth/token", json={"email": admin.email, "password": PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    response = client.post(
        "/api/admin/users",
        headers=headers,
        json={"email": "new@example.com", "name": "New", "password": PASSWORD, "role": "reviewer"},
    )
    assert response.status_code == 201
    assert "password" not in response.text
    assert (
        client.patch(
            "/api/admin/users/" + admin.id, headers=headers, json={"active": False}
        ).status_code
        == 409
    )


def test_unknown_and_wrong_password_have_identical_error(api):
    client, _, _ = api
    responses = [
        client.post("/api/auth/token", json={"email": email, "password": "wrong"})
        for email in ["member@example.com", "unknown@example.com"]
    ]
    assert all(r.status_code == 401 for r in responses)
    assert responses[0].json()["error"]["message"] == responses[1].json()["error"]["message"]


def test_untrusted_origin_cannot_log_browser_into_attackers_account(api):
    client, _, _ = api
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": PASSWORD},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
