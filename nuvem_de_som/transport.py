"""Pluggable HTTP transport for nuvem_de_som.

SoundCloud increasingly fingerprints HTTP clients (TLS/JA3, HTTP/2 frames,
header order) to gate API and HTML responses.  This module returns a session
object compatible with ``requests.Session`` — either the stdlib ``requests``
session or a ``curl_cffi`` session that impersonates a real browser.

Selection
---------
- If the environment variable ``NUVEM_TRANSPORT=curl_cffi`` is set AND
  ``curl_cffi`` is importable, ``default_session()`` returns
  ``curl_cffi.requests.Session(impersonate="chrome")``.
- Otherwise it returns ``requests.Session()``.

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
    ``NUVEM_TRANSPORT=curl_cffi`` is set and the package is importable;
    otherwise returns a plain ``requests.Session()``.
    """
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
