import importlib


def _load(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config.settings as s

    return importlib.reload(s)


def test_secure_cookies_follow_cookie_secure(monkeypatch):
    s = _load(monkeypatch, COOKIE_SECURE="true", SECURE_SSL_REDIRECT="true", SECURE_HSTS_SECONDS="3600")
    try:
        assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE
        assert s.SECURE_SSL_REDIRECT and s.SECURE_HSTS_SECONDS == 3600
        assert s.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    finally:
        _load(monkeypatch, COOKIE_SECURE="false", SECURE_SSL_REDIRECT="false", SECURE_HSTS_SECONDS="0")
