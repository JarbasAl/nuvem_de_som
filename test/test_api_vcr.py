"""Cassette-backed parser tests for ``SoundCloudAPI``.

Each public SoundCloud-hitting method has one test that asserts the
typed mediavocab return shape, that critical fields are populated, and
that the recent ``_parse_transcodings`` fix delivers a playable
progressive codec on a real track.

Re-record with::

    pytest --vcr-record=once test/test_api_vcr.py

Live re-validation runs nightly via ``.github/workflows/nightly-live.yml``.
"""
from __future__ import annotations

import pytest

from mediavocab import Entity, Release

from nuvem_de_som import SoundCloudAPI


pytestmark = pytest.mark.vcr


# Stable, reasonably popular targets used across the suite.
ARTIST_URL = "https://soundcloud.com/disclosuremusic"
TRACK_URL = "https://soundcloud.com/disclosuremusic/latch-ft-sam-smith"


def _first(it):
    for x in it:
        return x
    return None


def test_search_tracks_returns_releases():
    rel = _first(SoundCloudAPI().search_tracks("disclosure latch", limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.uri.startswith("https://soundcloud.com/")


def test_search_people_returns_entities():
    ent = _first(SoundCloudAPI().search_people("disclosure", limit=3))
    assert isinstance(ent, Entity)
    assert ent.name


def test_search_sets_returns_releases():
    rel = _first(SoundCloudAPI().search_sets("chillhop essentials", limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title


def test_get_tracks_from_artist_url():
    rel = _first(SoundCloudAPI().get_tracks(ARTIST_URL, limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.uri.startswith("https://soundcloud.com/")


def test_resolve_track_returns_release_with_progressive_codec():
    """Pins the ``_parse_transcodings`` progressive-over-HLS fix.

    Real SoundCloud tracks ship both progressive and HLS transcodings;
    after the fix, the parser must surface the progressive codec
    (``audio/mpeg``) rather than the HLS Opus/Ogg variant.
    """
    rel = SoundCloudAPI().resolve_track(TRACK_URL)
    assert isinstance(rel, Release)
    assert rel.work.title
    # progressive transcoding must win — direct, seekable MP3.
    assert rel.codec == "audio/mpeg", (
        f"expected progressive audio/mpeg, got {rel.codec!r} — the "
        "_parse_transcodings progressive-preference fix has regressed."
    )
    assert rel.bitrate in {"128", "256"}


def test_resolve_user_returns_entity():
    ent = SoundCloudAPI().resolve_user(ARTIST_URL)
    assert isinstance(ent, Entity)
    assert ent.name
    assert ent.external_ids.get("soundcloud_user_id")


def test_resolve_stream_returns_progressive_url():
    url = SoundCloudAPI().resolve_stream(TRACK_URL, prefer="progressive")
    assert isinstance(url, str)
    assert url.startswith("http")
