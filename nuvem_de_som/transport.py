"""Pluggable HTTP transport for nuvem_de_som.

SoundCloud increasingly fingerprints HTTP clients (TLS/JA3, HTTP/2 frames,
header order) to gate API and HTML responses.  This module returns a session
object compatible with ``requests.Session`` — one of three implementations,
selected in this order:

Selection
---------
1. ``NUVEM_TRANSPORT=curl_cffi`` set AND ``curl_cffi`` importable →
   ``curl_cffi.requests.Session(impersonate="chrome")``.
2. Otherwise, if ``unblock_requests`` is importable → its
   ``CloudflareSession`` (a drop-in ``requests.Session`` with anti-bot
   handling, an escalation ladder, and Wayback fallback). This is the
   default when the ``stealth`` extra is installed and no transport is
   forced via the environment.
3. Otherwise → plain ``requests.Session()``.

Users can also pass any compatible session directly via the ``session=`` kwarg
on :class:`nuvem_de_som.SoundCloudAPI`, :class:`nuvem_de_som.SoundCloudHTML`,
and the :class:`nuvem_de_som.SoundCloud` orchestrator.

Note: :class:`nuvem_de_som.SoundCloudYTDLP` uses yt-dlp internally for its
HTTP traffic and does NOT honour an injected session.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

ENV_VAR = "NUVEM_TRANSPORT"
CURL_CFFI = "curl_cffi"


def default_session():
    """Return a session object based on env config.

    Returns ``curl_cffi.requests.Session(impersonate="chrome")`` when
    ``NUVEM_TRANSPORT=curl_cffi`` is set and that package is importable.
    Otherwise prefers ``unblock_requests.CloudflareSession`` (a drop-in
    ``requests.Session`` with anti-bot and Wayback fallback) when the package
    is importable, falling back to a plain ``requests.Session()``.
    """
    if os.environ.get(ENV_VAR) != CURL_CFFI:
        try:
            from unblock_requests import CloudflareSession  # noqa: PLC0415
            return CloudflareSession(env_prefix="NUVEM", wayback_fallback=True)
        except Exception:
            pass
    if os.environ.get(ENV_VAR) == CURL_CFFI:
        try:
            from curl_cffi import requests as cffi_requests  # noqa: PLC0415
            return cffi_requests.Session(impersonate="chrome")
        except ImportError:
            log.warning(
                "%s=%s requested but curl_cffi is not installed; "
                "falling back to requests. Install with: "
                "pip install nuvem_de_som[stealth]",
                ENV_VAR, CURL_CFFI,
            )
    return requests.Session()
