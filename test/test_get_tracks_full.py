"""Integration tests for ``SoundCloudAPI`` — full-metadata listing and search.

After the mediavocab port, the API methods return ``Release`` and
``Entity`` objects rather than raw dicts. These tests exercise the live
SoundCloud endpoints; run with::

    pytest test/test_get_tracks_full.py -v -m integration
"""
import pytest
from mediavocab import Entity, Release

from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML


ARTIST_URL = "https://soundcloud.com/acidkid"
# acidkid is the URL slug; the real display name returned by the API is "Piratech"
ARTIST_DISPLAY_NAME = "Piratech"
SET_URL = "https://soundcloud.com/acidkid/sets/beathop"


def _release_artist(rel: Release) -> str:
    """Return the principal artist name on a Release, or ``""``."""
    if not rel.work.credits:
        return ""
    return rel.work.credits[0].entity.name


def _release_artist_url(rel: Release) -> str:
    return rel.work.extra.get("artist_url") or ""


def _assert_full_release(rel: Release) -> None:
    assert isinstance(rel, Release)
    assert rel.work.title, "release missing title"
    assert rel.uri.startswith("https://soundcloud.com/"), f"unexpected uri: {rel.uri}"
    assert _release_artist(rel), "release missing principal artist credit"
    assert _release_artist_url(rel).startswith("https://soundcloud.com/"), (
        f"unexpected artist_url: {_release_artist_url(rel)!r}"
    )


@pytest.mark.integration
def test_api_get_tracks_returns_tracks():
    sc = SoundCloudAPI()
    tracks = list(sc.get_tracks(ARTIST_URL, limit=50))
    assert len(tracks) > 0, "expected at least one track"
    for t in tracks:
        _assert_full_release(t)


@pytest.mark.integration
def test_api_get_tracks_more_than_html_scrape():
    """API pagination should yield at least as many tracks as HTML scraper."""
    html_tracks = list(SoundCloudHTML().get_tracks(ARTIST_URL))
    api_tracks = list(SoundCloudAPI().get_tracks(ARTIST_URL, limit=200))
    assert len(api_tracks) >= len(html_tracks), (
        f"expected api >= html: {len(api_tracks)} vs {len(html_tracks)}"
    )


@pytest.mark.integration
def test_api_get_tracks_real_artist_name():
    """API returns the display name, not the URL slug."""
    sc = SoundCloudAPI()
    tracks = list(sc.get_tracks(ARTIST_URL, limit=5))
    assert tracks, "no tracks returned"
    assert _release_artist(tracks[0]) == ARTIST_DISPLAY_NAME, (
        f"expected artist {ARTIST_DISPLAY_NAME!r}, got {_release_artist(tracks[0])!r}"
    )


@pytest.mark.integration
def test_api_get_tracks_has_artwork_and_duration():
    sc = SoundCloudAPI()
    tracks = list(sc.get_tracks(ARTIST_URL, limit=5))
    assert tracks, "no tracks returned"
    assert any(t.image for t in tracks), "expected at least one track with artwork"
    assert any(t.work.runtime for t in tracks), "expected at least one track with duration"


@pytest.mark.integration
def test_api_get_tracks_set_url():
    sc = SoundCloudAPI()
    tracks = list(sc.get_tracks(SET_URL, limit=50))
    assert len(tracks) > 0, "expected at least one track in set"
    for t in tracks:
        _assert_full_release(t)


@pytest.mark.integration
def test_api_get_tracks_respects_limit():
    sc = SoundCloudAPI()
    limit = 10
    tracks = list(sc.get_tracks(ARTIST_URL, limit=limit))
    assert len(tracks) <= limit, (
        f"expected at most {limit} tracks, got {len(tracks)}"
    )


@pytest.mark.integration
def test_api_search_tracks_returns_full_metadata():
    sc = SoundCloudAPI()
    tracks = list(sc.search_tracks("nuclear chill", limit=5))
    assert len(tracks) > 0, "expected at least one result"
    for t in tracks:
        _assert_full_release(t)
    assert any(t.image for t in tracks), "expected at least one track with artwork"
    assert any(t.work.runtime for t in tracks), "expected at least one track with duration"


@pytest.mark.integration
def test_api_search_people_returns_full_metadata():
    sc = SoundCloudAPI()
    people = list(sc.search_people("piratech", limit=5))
    assert len(people) > 0, "expected at least one result"
    for p in people:
        assert isinstance(p, Entity)
        assert p.name, "entity missing name"
        artist_url = p.extra.get("artist_url") or ""
        assert artist_url.startswith("https://soundcloud.com/"), (
            f"bad artist_url: {artist_url}"
        )
    assert any(p.extra.get("image") for p in people), "expected at least one artist with image"


@pytest.mark.integration
def test_factory_auto_search_tracks():
    """SoundCloud() auto-backend should return full-metadata tracks via API."""
    sc = SoundCloud()
    tracks = list(sc.search_tracks("nuclear chill", limit=5))
    assert len(tracks) > 0
    for t in tracks:
        assert isinstance(t, Release)
        assert t.work.title and t.uri


@pytest.mark.integration
def test_api_resolve_user():
    sc = SoundCloudAPI()
    info = sc.resolve_user(ARTIST_URL)
    assert info is not None, "resolve_user returned None"
    assert isinstance(info, Entity)
    assert info.name == ARTIST_DISPLAY_NAME, (
        f"expected {ARTIST_DISPLAY_NAME!r}, got {info.name!r}"
    )
    artist_url = info.extra.get("artist_url") or ""
    assert artist_url.startswith("https://soundcloud.com/")
    user_id = info.external_ids.get("soundcloud_user_id")
    assert user_id, "resolve_user must surface the soundcloud_user_id"


@pytest.mark.integration
def test_api_resolve_track():
    """A track URL must round-trip into the same Release shape as search_tracks."""
    sc = SoundCloudAPI()
    tracks = list(sc.get_tracks(ARTIST_URL, limit=1))
    assert tracks, "no tracks for canonical artist; cannot test resolve_track"
    track_url = tracks[0].uri
    info = sc.resolve_track(track_url)
    assert info is not None, f"resolve_track returned None for {track_url}"
    assert isinstance(info, Release)
    _assert_full_release(info)
    assert info.work.external_ids.get("soundcloud_track_id"), "missing soundcloud_track_id"
    assert info.work.credits and info.work.credits[0].entity.external_ids.get(
        "soundcloud_user_id"
    ), "missing soundcloud_user_id on principal credit"


@pytest.mark.integration
def test_api_resolve_track_returns_none_for_user_url():
    """A user permalink fed to resolve_track must return None, not a Release."""
    sc = SoundCloudAPI()
    assert sc.resolve_track(ARTIST_URL) is None
