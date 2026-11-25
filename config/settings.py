import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=""):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in ("1", "true", "yes")


def env_list(name, default=""):
    return [v.strip() for v in env(name, default).split(",") if v.strip()]


DEBUG = env_bool("DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is off.")
    SECRET_KEY = "insecure-dev-key-only-for-local-debug-use-0000"
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "django.contrib.postgres",
    "rest_framework_simplejwt.token_blacklist",
    "accounts",
    "catalog",
    "orders",
    "bookings",
    "payments",
]

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

_db = urlparse(env("DATABASE_URL", "postgres://air_roam:air_roam@localhost:5433/air_roam"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": _db.port or 5432,
    }
}

if env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": env("REDIS_URL")}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "EXCEPTION_HANDLER": "common.errors.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "config.pagination.Pagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"auth": "5/min", "user": "120/min"},
    # 0 = trust only REMOTE_ADDR (X-Forwarded-For can't be spoofed); set to the number of proxies when deployed.
    "NUM_PROXIES": int(env("NUM_PROXIES", "0") or 0),
}

SPECTACULAR_SETTINGS = {"TITLE": "Air Roam API", "VERSION": "1.0.0"}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": SECRET_KEY,
}

COOKIE_SECURE = env_bool("COOKIE_SECURE", True)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN") or None
SESSION_COOKIE_SECURE = COOKIE_SECURE
# Production behind a TLS-terminating proxy (e.g. Cloudflare): enable via env when hosting is set up.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "0") or 0)

WEB_STORE_URL = env("WEB_STORE_URL", "http://localhost:5173")
APP_DEEP_LINK = env("APP_DEEP_LINK", "airroam://payment-result")
PAYMONGO_SECRET_KEY = env("PAYMONGO_SECRET_KEY")
PAYMONGO_WEBHOOK_SECRET = env("PAYMONGO_WEBHOOK_SECRET")
PAYMONGO_METHODS = env_list("PAYMONGO_METHODS", "gcash,paymaya,qrph,card")  # only methods enabled on the account
WEB_REBUILD_HOOK_URL = env("WEB_REBUILD_HOOK_URL")

ADMIN_ENABLED = env_bool("ADMIN_ENABLED")
ADMIN_URL = env("ADMIN_URL", "dev-admin/")
