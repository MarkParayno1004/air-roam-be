import pytest


@pytest.fixture(autouse=True)
def origins(settings):
    settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:5174"]


def _preflight(client, origin):
    return client.options("/api/v1/products", HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")


def test_cors_allows_store_origin_with_credentials(client):
    r = _preflight(client, "http://localhost:5173")
    assert r["access-control-allow-origin"] == "http://localhost:5173"
    assert r["access-control-allow-credentials"] == "true"


def test_cors_allows_admin_origin(client):
    assert _preflight(client, "http://localhost:5174")["access-control-allow-origin"] == "http://localhost:5174"


def test_cors_blocks_unknown_origin(client):
    assert "access-control-allow-origin" not in _preflight(client, "http://evil.test")


def test_csrf_cookie_is_strict(settings):
    assert settings.CSRF_COOKIE_SAMESITE == "Strict"
