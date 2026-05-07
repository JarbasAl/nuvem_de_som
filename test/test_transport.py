"""Tests for nuvem_de_som.transport and session injection."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
import requests

from nuvem_de_som import SoundCloudAPI, SoundCloudHTML, SoundCloud
from nuvem_de_som import transport as transport_mod


# ---------------------------------------------------------------------------
# default_session() env-var behaviour
# ---------------------------------------------------------------------------

def test_default_session_no_env_returns_requests_session(monkeypatch):
    monkeypatch.delenv(transport_mod.ENV_VAR, raising=False)
    s = transport_mod.default_session()
    assert isinstance(s, requests.Session)


def test_default_session_env_falls_back_when_curl_cffi_missing(monkeypatch):
    """When NUVEM_TRANSPORT=curl_cffi but the package is absent, fall back."""
    monkeypatch.setenv(transport_mod.ENV_VAR, transport_mod.CURL_CFFI)
    # Ensure curl_cffi can't be imported
    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    s = transport_mod.default_session()
    assert isinstance(s, requests.Session)


def test_default_session_env_uses_curl_cffi_when_present(monkeypatch):
    """When NUVEM_TRANSPORT=curl_cffi and the package imports, use it."""
    monkeypatch.setenv(transport_mod.ENV_VAR, transport_mod.CURL_CFFI)

    sentinel = object()
    fake_requests_mod = types.SimpleNamespace(
        Session=MagicMock(return_value=sentinel)
    )
    fake_curl_cffi = types.ModuleType("curl_cffi")
    fake_curl_cffi.requests = fake_requests_mod
    monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl_cffi)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_requests_mod)

    s = transport_mod.default_session()
    assert s is sentinel
    fake_requests_mod.Session.assert_called_once_with(impersonate="chrome")


# ---------------------------------------------------------------------------
# Session injection — captures calls
# ---------------------------------------------------------------------------

def _mk_session_response(json_data=None, text="", content=b"", status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


def test_soundcloud_api_uses_injected_session():
    sess = MagicMock()
    sess.get.return_value = _mk_session_response(json_data={"collection": []})

    api = SoundCloudAPI(session=sess)
    assert api.session is sess

    # Pre-seed client_id to avoid the bootstrap request
    import nuvem_de_som as nds
    nds._CLIENT_ID = "x" * 32
    try:
        list(api.search_tracks("foo", limit=1))
    finally:
        nds._CLIENT_ID = None

    # The injected session was the one called
    assert sess.get.called
    called_url = sess.get.call_args.args[0]
    assert "api-v2.soundcloud.com" in called_url


def test_soundcloud_html_uses_injected_session():
    sess = MagicMock()
    sess.get.return_value = _mk_session_response(content=b"<html></html>")

    html = SoundCloudHTML(session=sess)
    assert html.session is sess
    list(html.search_tracks("foo", limit=1))

    assert sess.get.called
    called_url = sess.get.call_args.args[0]
    assert "soundcloud.com/search/sounds" in called_url


def test_soundcloud_orchestrator_propagates_session_to_subbackends():
    sess = MagicMock()
    sc = SoundCloud(session=sess)
    api = next(b for b in sc._chain if isinstance(b, SoundCloudAPI))
    html = next(b for b in sc._chain if isinstance(b, SoundCloudHTML))
    assert api.session is sess
    assert html.session is sess


def test_default_constructors_pick_up_default_session(monkeypatch):
    """Without args, classes use transport.default_session()."""
    monkeypatch.delenv(transport_mod.ENV_VAR, raising=False)
    api = SoundCloudAPI()
    html = SoundCloudHTML()
    assert isinstance(api.session, requests.Session)
    assert isinstance(html.session, requests.Session)
