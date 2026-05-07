"""Cassette-backed parser tests for ``SoundCloudHTML`` scraper.

Pinned against the schema.org/Open Graph markup the scraper depends on,
so silent upstream HTML changes surface here rather than as empty
results in production.

Re-record with::

    pytest --vcr-record=once test/test_html_vcr.py
"""
from __future__ import annotations

import pytest

from mediavocab import Entity, Release

from nuvem_de_som import SoundCloudHTML


pytestmark = pytest.mark.vcr


ARTIST_URL = "https://soundcloud.com/disclosuremusic"
TRACK_URL = "https://soundcloud.com/disclosuremusic/latch-ft-sam-smith"


def _first(it):
    for x in it:
        return x
    return None


def test_search_tracks_returns_releases():
    rel = _first(SoundCloudHTML().search_tracks("disclosure latch", limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.uri.startswith("https://soundcloud.com/")


def test_search_people_returns_entities():
    ent = _first(SoundCloudHTML().search_people("disclosure", limit=3))
    assert isinstance(ent, Entity)
    assert ent.name
    assert (ent.extra.get("artist_url") or "").startswith("https://soundcloud.com/")


def test_search_sets_returns_releases():
    rel = _first(SoundCloudHTML().search_sets("chillhop essentials", limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title


def test_get_tracks_from_artist_page():
    rel = _first(SoundCloudHTML().get_tracks(ARTIST_URL, limit=3))
    assert isinstance(rel, Release)
    assert rel.work.title


def test_resolve_user_returns_entity():
    ent = SoundCloudHTML().resolve_user(ARTIST_URL)
    assert isinstance(ent, Entity)
    assert ent.name


def test_resolve_track_returns_release():
    rel = SoundCloudHTML().resolve_track(TRACK_URL)
    assert isinstance(rel, Release)
    assert rel.work.title


def test_get_track_meta_returns_artist_and_image():
    meta = SoundCloudHTML().get_track_meta(TRACK_URL)
    # at minimum one of the two should be populated on a real track page
    assert meta.get("artist") or meta.get("image")


def test_search_tracks_enriched_yields_releases():
    rel = _first(SoundCloudHTML().search_tracks_enriched("disclosure latch", limit=2))
    assert isinstance(rel, Release)
    assert rel.work.title
