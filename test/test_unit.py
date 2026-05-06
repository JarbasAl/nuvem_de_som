"""Unit tests — no network access required."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP
from nuvem_de_som import _invalidate_client_id, _get_client_id


# ---------------------------------------------------------------------------
# SoundCloudHTML._parse_duration
# ---------------------------------------------------------------------------

class TestParseDuration:
    def test_full(self):
        assert SoundCloudHTML._parse_duration("PT01H02M03S") == 3723

    def test_minutes_and_seconds(self):
        assert SoundCloudHTML._parse_duration("PT03M09S") == 189

    def test_hours_only(self):
        assert SoundCloudHTML._parse_duration("PT01H") == 3600

    def test_seconds_only(self):
        assert SoundCloudHTML._parse_duration("PT30S") == 30

    def test_zero_padded(self):
        assert SoundCloudHTML._parse_duration("PT00H03M09S") == 189

    def test_none_input(self):
        assert SoundCloudHTML._parse_duration(None) is None

    def test_empty_string(self):
        assert SoundCloudHTML._parse_duration("") is None

    def test_invalid_string(self):
        assert SoundCloudHTML._parse_duration("INVALID") is None

    def test_bare_pt(self):
        # "PT" with no components should not return 0
        assert SoundCloudHTML._parse_duration("PT") is None

    def test_non_iso(self):
        assert SoundCloudHTML._parse_duration("3:09") is None


# ---------------------------------------------------------------------------
# SoundCloudAPI._parse_track — canonical key set
# ---------------------------------------------------------------------------

class TestParseTrack:
    def _track(self, **overrides):
        base = {
            "title": "Test Track",
            "permalink_url": "https://soundcloud.com/user/track",
            "duration": 180000,
            "artwork_url": "https://example.com/art.jpg",
            "user": {
                "username": "Artist",
                "permalink_url": "https://soundcloud.com/user",
                "avatar_url": "https://example.com/avatar.jpg",
            },
        }
        base.update(overrides)
        return base

    def test_all_keys_present(self):
        result = SoundCloudAPI._parse_track(self._track())
        for key in ("title", "url", "artist", "artist_url", "image", "duration"):
            assert key in result, f"missing key: {key!r}"

    def test_duration_converted_to_seconds(self):
        result = SoundCloudAPI._parse_track(self._track(duration=180000))
        assert result["duration"] == 180

    def test_missing_duration_is_none(self):
        result = SoundCloudAPI._parse_track(self._track(duration=None))
        assert result["duration"] is None

    def test_artwork_falls_back_to_avatar(self):
        t = self._track()
        t["artwork_url"] = None
        result = SoundCloudAPI._parse_track(t)
        assert result["image"] == "https://example.com/avatar.jpg"

    def test_missing_user(self):
        t = self._track()
        t["user"] = None
        result = SoundCloudAPI._parse_track(t)
        assert result["artist"] == ""
        assert result["artist_url"] == ""

    def test_artist_url_override(self):
        result = SoundCloudAPI._parse_track(self._track(),
                                            artist_url="https://soundcloud.com/override")
        assert result["artist_url"] == "https://soundcloud.com/override"


# ---------------------------------------------------------------------------
# SoundCloudHTML.search_tracks — canonical key set
# ---------------------------------------------------------------------------

class TestHTMLSearchTracksKeySet:
    """All track results from HTML backend must be mediavocab Release objects."""

    def _fake_soup_h2(self, href="/user/track", text="Track Title"):
        from bs4 import BeautifulSoup
        html = f'<h2><a href="{href}">{text}</a></h2>'
        return BeautifulSoup(html, "html.parser")

    def test_search_tracks_returns_release(self):
        from mediavocab import Release
        sc = SoundCloudHTML()
        soup = self._fake_soup_h2()
        with patch.object(SoundCloudHTML, "_get_soup", return_value=soup):
            results = list(sc.search_tracks("test", limit=1))
        assert results, "expected at least one result"
        assert isinstance(results[0], Release)

    def test_search_tracks_missing_values_are_empty(self):
        sc = SoundCloudHTML()
        soup = self._fake_soup_h2()
        with patch.object(SoundCloudHTML, "_get_soup", return_value=soup):
            results = list(sc.search_tracks("test", limit=1))
        t = results[0]
        assert t.work.credits == []
        assert t.image == ""
        assert t.work.runtime is None


# ---------------------------------------------------------------------------
# resolve_stream — prefer validation
# ---------------------------------------------------------------------------

class TestPreferValidation:
    def test_api_invalid_prefer_raises(self):
        sc = SoundCloudAPI()
        with pytest.raises(ValueError, match="prefer"):
            sc.resolve_stream("https://soundcloud.com/user/track", prefer="invalid")

    def test_html_resolve_stream_not_implemented(self):
        sc = SoundCloudHTML()
        with pytest.raises(NotImplementedError):
            sc.resolve_stream("https://soundcloud.com/user/track")

    def test_ytdlp_invalid_prefer_raises(self):
        sc = SoundCloudYTDLP()
        with pytest.raises(ValueError, match="prefer"):
            sc.resolve_stream("https://soundcloud.com/user/track", prefer="mp3")

    def test_orchestrator_invalid_prefer_raises(self):
        sc = SoundCloud()
        with pytest.raises(ValueError, match="prefer"):
            sc.resolve_stream("https://soundcloud.com/user/track", prefer="nope")

    def test_progressive_accepted(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", return_value={}):
            result = sc.resolve_stream("https://soundcloud.com/user/track",
                                       prefer="progressive")
        assert result is None  # no transcodings in mock, but no exception

    def test_hls_accepted(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", return_value={}):
            result = sc.resolve_stream("https://soundcloud.com/user/track", prefer="hls")
        assert result is None


# ---------------------------------------------------------------------------
# client_id thread safety
# ---------------------------------------------------------------------------

class TestClientIdThreadSafety:
    def test_concurrent_calls_dont_duplicate_fetch(self):
        _invalidate_client_id()
        fetch_count = {"n": 0}

        def counting_fetch():
            fetch_count["n"] += 1
            return "fakeclientid00000000000000000001"

        with patch("nuvem_de_som._fetch_client_id", side_effect=counting_fetch):
            _invalidate_client_id()
            threads = [threading.Thread(target=_get_client_id) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # With the lock in place, _fetch_client_id should only be called once
        assert fetch_count["n"] == 1


# ---------------------------------------------------------------------------
# SoundCloudAPI.get_tracks — page size respects limit
# ---------------------------------------------------------------------------

class TestGetTracksPageSize:
    def test_page_size_capped_at_limit(self):
        sc = SoundCloudAPI()
        calls = []

        def fake_call(endpoint, **params):
            calls.append((endpoint, params))
            if "resolve" in endpoint:
                return {"kind": "user", "id": 123,
                        "permalink_url": "https://soundcloud.com/user"}
            # user tracks endpoint
            return {"collection": [], "next_href": None}

        with patch.object(sc, "_call", side_effect=fake_call):
            list(sc.get_tracks("https://soundcloud.com/user", limit=5))

        # Find the tracks page call
        tracks_calls = [(ep, p) for ep, p in calls if "tracks" in ep]
        assert tracks_calls, "expected at least one tracks page call"
        _, params = tracks_calls[0]
        assert params["limit"] <= 5, (
            f"expected page size <= 5, got {params['limit']}"
        )

    def test_stops_at_limit(self):
        sc = SoundCloudAPI()

        def fake_call(endpoint, **params):
            if "resolve" in endpoint:
                return {"kind": "user", "id": 1,
                        "permalink_url": "https://soundcloud.com/user"}
            tracks = [{"title": f"t{i}", "permalink_url": f"https://soundcloud.com/user/t{i}",
                       "duration": 60000, "artwork_url": "", "user": {"username": "u",
                       "permalink_url": "https://soundcloud.com/user", "avatar_url": ""}}
                      for i in range(50)]
            return {"collection": tracks, "next_href": "https://next"}

        with patch.object(sc, "_call", side_effect=fake_call):
            results = list(sc.get_tracks("https://soundcloud.com/user", limit=7))

        assert len(results) == 7


# ---------------------------------------------------------------------------
# SoundCloud orchestrator — fallback chain
# ---------------------------------------------------------------------------

class TestOrchestratorFallback:
    def test_falls_through_to_second_backend_on_error(self):
        sc = SoundCloud()
        api, ytdlp, html = sc._chain

        with patch.object(api, "search_tracks", side_effect=RuntimeError("API down")):
            with patch.object(ytdlp, "search_tracks",
                              return_value=iter([{"title": "t", "url": "u",
                                                  "artist": "", "artist_url": "",
                                                  "image": "", "duration": None}])):
                results = list(sc.search_tracks("test"))

        assert len(results) == 1
        assert results[0]["title"] == "t"

    def test_empty_result_falls_through(self):
        sc = SoundCloud()
        api, ytdlp, html = sc._chain

        with patch.object(api, "search_tracks", return_value=iter([])):
            with patch.object(ytdlp, "search_tracks", return_value=iter([])):
                with patch.object(html, "search_tracks",
                                  return_value=iter([{"title": "html", "url": "u",
                                                      "artist": "", "artist_url": "",
                                                      "image": "", "duration": None}])):
                    results = list(sc.search_tracks("test"))

        assert results[0]["title"] == "html"

    def test_resolve_stream_returns_first_non_none(self):
        sc = SoundCloud()
        api, ytdlp, html = sc._chain

        with patch.object(api, "resolve_stream", return_value=None):
            with patch.object(ytdlp, "resolve_stream", return_value="https://stream.url"):
                result = sc.resolve_stream("https://soundcloud.com/user/track")

        assert result == "https://stream.url"


# ---------------------------------------------------------------------------
# download_tracks — omits failures (only available on SoundCloudYTDLP / SoundCloud)
# ---------------------------------------------------------------------------

class TestDownloadTracks:
    def test_failed_download_omitted(self):
        """download_tracks() skips None returns — only on SoundCloudYTDLP."""
        sc = SoundCloudYTDLP()
        urls = ["https://soundcloud.com/user/a", "https://soundcloud.com/user/b"]
        returns = [None, Path("/tmp/b.mp3")]

        with patch.object(sc, "download_track", side_effect=returns):
            results = sc.download_tracks(urls)

        assert results == [Path("/tmp/b.mp3")]
        assert len(results) == 1

    def test_orchestrator_delegates_to_ytdlp(self):
        """SoundCloud.download_track() delegates to the SoundCloudYTDLP backend."""
        sc = SoundCloud()
        ytdlp_backend = sc._ytdlp
        expected = Path("/tmp/track.mp3")

        with patch.object(ytdlp_backend, "download_track", return_value=expected) as m:
            result = sc.download_track("https://soundcloud.com/user/track")

        assert result == expected
        m.assert_called_once_with(
            "https://soundcloud.com/user/track",
            output_dir=".", verbose=False,
        )

    def test_api_backend_has_download_methods(self):
        """SoundCloudAPI exposes download_track/tracks/playlist (pure requests, no yt-dlp)."""
        sc = SoundCloudAPI()
        assert hasattr(sc, "download_track")
        assert hasattr(sc, "download_tracks")
        assert hasattr(sc, "download_playlist")

    def test_html_backend_has_no_download_methods(self):
        """SoundCloudHTML should not have download methods."""
        sc = SoundCloudHTML()
        assert not hasattr(sc, "download_track"), (
            "SoundCloudHTML should not expose download_track"
        )
