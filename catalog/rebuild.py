import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def trigger_rebuild():
    """Ask the web store host to rebuild pre-rendered pages. Never raises."""
    url = settings.WEB_REBUILD_HOOK_URL
    if not url:
        return
    try:
        requests.post(url, timeout=5)
    except Exception:  # a failed rebuild must never break a catalog save
        log.exception("web store rebuild hook failed")
