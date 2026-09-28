from fastapi.testclient import TestClient

from flowpilot.app import create_app
from flowpilot.config import Settings


def test_liveness_does_not_require_database():
    settings = Settings(database_url="postgresql+psycopg://invalid@127.0.0.1:1/unavailable")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "integration-123"})
        assert response.status_code == 200
        assert response.json()["service"] == "flowpilot"
        assert response.headers["X-Request-ID"] == "integration-123"


def test_readiness_fails_without_database_and_does_not_leak_connection_info():
    settings = Settings(database_url="postgresql+psycopg://invalid:SECRET@127.0.0.1:1/unavailable")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unavailable"
        assert "SECRET" not in response.text


def test_request_id_is_validated_and_cors_is_explicit():
    with TestClient(create_app(Settings())) as client:
        response = client.get(
            "/health/live",
            headers={
                "X-Request-ID": "not a valid request id",
                "Origin": "https://untrusted.example",
            },
        )
        assert response.headers["X-Request-ID"] != "not a valid request id"
        assert "access-control-allow-origin" not in response.headers


def test_not_found_has_consistent_error_envelope():
    with TestClient(create_app(Settings())) as client:
        response = client.get("/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "http_404"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_body_limit_applies_before_parsing_even_without_content_length():
    with TestClient(create_app(Settings(upload_limit_bytes=10))) as client:
        response = client.post("/api/auth/token", content=b"x" * 1_000_011)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"
