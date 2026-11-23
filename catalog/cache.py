"""Public catalog response cache. Keys embed a version number; bumping it invalidates everything (works on any cache backend)."""
from django.core.cache import cache

TTL = 60
_VERSION_KEY = "catalog:version"


def _version():
    return cache.get_or_set(_VERSION_KEY, 1, None)


def get_or_build(name, build):
    key = f"catalog:{_version()}:{name}"
    data = cache.get(key)
    if data is None:
        data = build()
        cache.set(key, data, TTL)
    return data


def invalidate():
    cache.set(_VERSION_KEY, _version() + 1, None)
