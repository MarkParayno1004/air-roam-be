def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_schema(client):
    assert client.get("/api/schema/").status_code == 200


def test_admin_hidden_when_disabled(settings):
    from config.urls import build_urlpatterns

    settings.ADMIN_ENABLED = False
    assert not any("admin" in str(p.pattern) for p in build_urlpatterns())


def test_admin_shown_when_enabled(settings):
    from config.urls import build_urlpatterns

    settings.ADMIN_ENABLED = True
    settings.ADMIN_URL = "dev-admin/"
    assert any(str(p.pattern) == "dev-admin/" for p in build_urlpatterns())
