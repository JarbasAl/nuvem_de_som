"""Extra unit tests targeting branches not covered by VCR cassettes.

All tests are offline — network IO is stubbed with unittest.mock.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from bs4 import BeautifulSoup

from nuvem_de_som import (
    SoundCloud,
    SoundCloudAPI,
    SoundCloudHTML,
    SoundCloudYTDLP,
    _build_genres,
    _empty_track,
    _fetch_client_id,
    _get_client_id,
    _invalidate_client_id,
    _parse_transcodings,
    _sc_user_to_dict,
    _set_dict_to_release,
    _track_dict_to_release,
    _user_dict_to_entity,
    _ydl_import,
)
from nuvem_de_som import transport as nds_transport


# ---------------------------------------------------------------------------
# _sc_user_to_dict — field mapping
# ---------------------------------------------------------------------------

class TestScUserToDict:
    def _raw(self, **overrides):
        base = {
            "username": "Noisia",
            "permalink_url": "https://soundcloud.com/noisia",
            "avatar_url": "https://img/noisia.jpg",
            "id": 42,
            "country_code": "NL",
            "permalink": "noisia",
            "verified": True,
            "followers_count": 500000,
            "followings_count": 120,
            "track_count": 88,
        }
        base.update(overrides)
        return base

    def test_maps_verified(self):
        d = _sc_user_to_dict(self._raw(verified=True))
        assert d["verified"] is True

    def test_verified_false(self):
        d = _sc_user_to_dict(self._raw(verified=False))
        assert d["verified"] is False

    def test_maps_followers_count(self):
        d = _sc_user_to_dict(self._raw(followers_count=12345))
        assert d["followers_count"] == 12345

    def test_maps_followings_count(self):
        d = _sc_user_to_dict(self._raw(followings_count=99))
        assert d["followings_count"] == 99

    def test_maps_track_count(self):
        d = _sc_user_to_dict(self._raw(track_count=55))
        assert d["track_count"] == 55

    def test_missing_counts_are_none(self):
        raw = {"username": "X"}
        d = _sc_user_to_dict(raw)
        assert d["followers_count"] is None
        assert d["followings_count"] is None
        assert d["track_count"] is None

    def test_artist_url_override(self):
        d = _sc_user_to_dict(self._raw(), artist_url="https://override")
        assert d["artist_url"] == "https://override"


class TestUserDictToEntityExtra:
    def test_verified_surfaces_in_extra(self):
        d = {"artist": "X", "verified": True, "followers_count": 100}
        ent = _user_dict_to_entity(d)
        assert ent.extra.get("verified") == "1"

    def test_unverified_absent_from_extra(self):
        d = {"artist": "X", "verified": False}
        ent = _user_dict_to_entity(d)
        assert "verified" not in ent.extra

    def test_followers_count_in_extra(self):
        d = {"artist": "X", "followers_count": 9999}
        ent = _user_dict_to_entity(d)
        assert ent.extra.get("followers_count") == "9999"

    def test_followings_count_in_extra(self):
        d = {"artist": "X", "followings_count": 77}
        ent = _user_dict_to_entity(d)
        assert ent.extra.get("followings_count") == "77"

    def test_track_count_in_extra(self):
        d = {"artist": "X", "track_count": 33}
        ent = _user_dict_to_entity(d)
        assert ent.extra.get("track_count") == "33"

    def test_none_counts_absent_from_extra(self):
        d = {"artist": "X", "followers_count": None,
             "followings_count": None, "track_count": None}
        ent = _user_dict_to_entity(d)
        assert "followers_count" not in ent.extra
        assert "followings_count" not in ent.extra
        assert "track_count" not in ent.extra

    def test_zero_count_present_in_extra(self):
        d = {"artist": "X", "followers_count": 0}
        ent = _user_dict_to_entity(d)
        assert ent.extra.get("followers_count") == "0"


# ---------------------------------------------------------------------------
# converters / pure helpers
# ---------------------------------------------------------------------------

class TestEmptyTrack:
    def test_default(self):
        d = _empty_track()
        assert d["url"] == ""
        for k in ("title", "artist", "artist_url", "image"):
            assert d[k] == ""
        assert d["duration"] is None

    def test_with_url(self):
        d = _empty_track("https://x")
        assert d["url"] == "https://x"


class TestTrackDictRoundtrip:
    def test_blank_returns_release(self):
        rel = _track_dict_to_release({})
        assert rel.uri == ""
        assert rel.work.title == ""

    def test_user_id_set_no_artist_no_credits(self):
        rel = _track_dict_to_release({"user_id": 9})
        assert rel.work.credits == []
        assert rel.work.external_ids["soundcloud_user_id"] == "9"


class TestUserDictRoundtrip:
    def test_no_country(self):
        ent = _user_dict_to_entity({"artist": "X"})
        assert ent.name == "X"
        assert "country" not in ent.extra

    def test_with_country(self):
        ent = _user_dict_to_entity({"artist": "X", "country": "PT"})
        assert ent.extra["country"] == "PT"


class TestSetDictRoundtrip:
    def test_skips_untitled_tracks(self):
        rel = _set_dict_to_release({
            "title": "S", "url": "u", "playlist_id": 1,
            "tracks": [{"title": ""}, {"title": "Real",
                                       "url": "https://x/a/b"}],
        })
        assert len(rel.work.tracklist) == 1
        assert rel.work.tracklist[0].work.title == "Real"


class TestBuildGenresEdges:
    def test_quoted_token_only(self):
        # the quoted-tag branch → q-arm
        out = _build_genres(None, '"hip hop"')
        assert any("hip" in g for g in out)


class TestParseTranscodingsEdges:
    def test_missing_quality(self):
        codec, br = _parse_transcodings([
            {"format": {"mime_type": "audio/mpeg", "protocol": "progressive"}}
        ])
        assert codec == "audio/mpeg"
        assert br == ""

    def test_single_entry_no_format(self):
        codec, br = _parse_transcodings([{"quality": "hq"}])
        assert codec == ""
        assert br == "256"

    def test_mixed_protocols_picks_progressive(self):
        codec, br = _parse_transcodings([
            {"format": {"mime_type": "audio/ogg", "protocol": "hls"},
             "quality": "hq"},
            {"format": {"mime_type": "audio/mpeg", "protocol": "progressive"},
             "quality": "sq"},
        ])
        assert codec == "audio/mpeg"
        assert br == "128"

    def test_unknown_quality(self):
        codec, br = _parse_transcodings([
            {"format": {"mime_type": "audio/mpeg",
                        "protocol": "progressive"}, "quality": "wat"}
        ])
        assert br == ""


# ---------------------------------------------------------------------------
# client_id fetching — both branches
# ---------------------------------------------------------------------------

class TestFetchClientId:
    def setup_method(self):
        _invalidate_client_id()

    def teardown_method(self):
        _invalidate_client_id()

    def test_extracts_from_js(self):
        homepage = MagicMock(text=(
            '<html><script src="https://a-v2.sndcdn.com/assets/0.js"></script>'
            '<script src="https://a-v2.sndcdn.com/assets/1.js"></script></html>'
        ))
        homepage.raise_for_status.return_value = None
        bundle_no_match = MagicMock(text="nothing here")
        bundle_match = MagicMock(text='client_id:"abcdef0123456789abcdef0123456789"')

        # First .get is homepage; then bundles in reversed order.
        gets = [homepage, bundle_match]

        def fake_get(url, **kw):
            return gets.pop(0)

        s = MagicMock()
        s.get.side_effect = fake_get
        cid = _fetch_client_id(session=s)
        assert cid == "abcdef0123456789abcdef0123456789"

    def test_request_exception_skipped(self):
        homepage = MagicMock(text=(
            '<script src="https://a-v2.sndcdn.com/assets/0.js"></script>'
            '<script src="https://a-v2.sndcdn.com/assets/1.js"></script>'
        ))
        homepage.raise_for_status.return_value = None
        good = MagicMock(text='"client_id":"abcdef0123456789abcdef0123456789"')

        calls = {"n": 0}

        def fake_get(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return homepage
            if calls["n"] == 2:
                raise requests.RequestException("boom")
            return good

        s = MagicMock()
        s.get.side_effect = fake_get
        cid = _fetch_client_id(session=s)
        assert cid == "abcdef0123456789abcdef0123456789"

    def test_no_match_raises(self):
        homepage = MagicMock(text='<script src="https://x/a.js"></script>')
        homepage.raise_for_status.return_value = None
        bundle = MagicMock(text="no match here")
        s = MagicMock()
        s.get.side_effect = [homepage, bundle]
        with pytest.raises(RuntimeError, match="client_id"):
            _fetch_client_id(session=s)

    def test_default_path_uses_requests_module(self):
        with patch("nuvem_de_som.requests.get") as g:
            g.side_effect = [
                MagicMock(text='<script src="https://x/a.js"></script>',
                          raise_for_status=lambda: None),
                MagicMock(text='client_id=abcdef0123456789abcdef0123456789'),
            ]
            cid = _fetch_client_id(session=None)
            assert cid == "abcdef0123456789abcdef0123456789"

    def test_get_client_id_caches(self):
        with patch("nuvem_de_som._fetch_client_id",
                   return_value="abcdef0123456789abcdef0123456789"):
            a = _get_client_id()
            b = _get_client_id()
            assert a == b


# ---------------------------------------------------------------------------
# transport selection
# ---------------------------------------------------------------------------

class TestTransport:
    def test_default_returns_requests_session(self, monkeypatch):
        monkeypatch.delenv(nds_transport.ENV_VAR, raising=False)
        s = nds_transport.default_session()
        assert isinstance(s, requests.Session)

    def test_curl_cffi_missing_falls_back(self, monkeypatch):
        monkeypatch.setenv(nds_transport.ENV_VAR, nds_transport.CURL_CFFI)
        # Ensure the import inside default_session fails.
        with patch.dict(sys.modules, {"curl_cffi": None}):
            s = nds_transport.default_session()
        assert isinstance(s, requests.Session)


# ---------------------------------------------------------------------------
# _ydl_import
# ---------------------------------------------------------------------------

class TestYdlImport:
    def test_missing_raises_helpful(self):
        with patch.dict(sys.modules, {"yt_dlp": None}):
            with pytest.raises(ImportError, match="yt-dlp is required"):
                _ydl_import()

    def test_present_returns_module(self):
        fake = MagicMock()
        with patch.dict(sys.modules, {"yt_dlp": fake}):
            assert _ydl_import() is fake


# ---------------------------------------------------------------------------
# SoundCloudAPI._call retry logic + error paths
# ---------------------------------------------------------------------------

class TestApiCall:
    def test_retries_on_401(self):
        sc = SoundCloudAPI()
        sc.session = MagicMock()
        first = MagicMock(status_code=401)
        first.json.return_value = {}
        second = MagicMock(status_code=200)
        second.json.return_value = {"ok": True}
        second.raise_for_status.return_value = None
        sc.session.get.side_effect = [first, second]
        with patch("nuvem_de_som._get_client_id", return_value="x"):
            with patch("nuvem_de_som._invalidate_client_id"):
                result = sc._call("https://api/x")
        assert result == {"ok": True}

    def test_passes_through_on_200(self):
        sc = SoundCloudAPI()
        sc.session = MagicMock()
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"a": 1}
        ok.raise_for_status.return_value = None
        sc.session.get.return_value = ok
        with patch("nuvem_de_som._get_client_id", return_value="x"):
            assert sc._call("https://api/x") == {"a": 1}


# ---------------------------------------------------------------------------
# SoundCloudAPI.get_tracks branches
# ---------------------------------------------------------------------------

class TestGetTracksBranches:
    def test_unknown_kind(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call",
                          return_value={"kind": "unknown"}):
            assert list(sc.get_tracks("https://soundcloud.com/x")) == []

    def test_playlist_skips_untitled(self):
        sc = SoundCloudAPI()
        playlist = {
            "kind": "playlist",
            "user": {"permalink_url": "https://soundcloud.com/u"},
            "tracks": [
                {"title": ""},
                {"title": "Real", "permalink_url": "https://x/a/b",
                 "user": {"username": "U"}},
            ],
        }
        with patch.object(sc, "_call", return_value=playlist):
            results = list(sc.get_tracks("https://x", limit=10))
        assert len(results) == 1
        assert results[0].work.title == "Real"

    def test_playlist_respects_limit(self):
        sc = SoundCloudAPI()
        playlist = {
            "kind": "playlist",
            "user": {},
            "tracks": [{"title": f"t{i}", "permalink_url": "u"}
                       for i in range(10)],
        }
        with patch.object(sc, "_call", return_value=playlist):
            results = list(sc.get_tracks("https://x", limit=3))
        assert len(results) == 3


# ---------------------------------------------------------------------------
# SoundCloudAPI.resolve_stream — both prefer modes, transcoding selection
# ---------------------------------------------------------------------------

class TestApiResolveStream:
    def test_returns_progressive_url(self):
        sc = SoundCloudAPI()
        resource = {
            "media": {
                "transcodings": [
                    {"url": "https://api/hls", "format": {"protocol": "hls"}},
                    {"url": "https://api/prog",
                     "format": {"protocol": "progressive"}},
                ]
            }
        }
        def fake_call(endpoint, **kw):
            if "resolve" in endpoint:
                return resource
            return {"url": "https://stream/file.mp3"}

        with patch.object(sc, "_call", side_effect=fake_call):
            url = sc.resolve_stream("https://x")
        assert url == "https://stream/file.mp3"

    def test_returns_none_when_no_url(self):
        sc = SoundCloudAPI()
        resource = {"media": {"transcodings": [{"format": {"protocol": "hls"}}]}}
        with patch.object(sc, "_call", return_value=resource):
            assert sc.resolve_stream("https://x") is None

    def test_skips_empty_url_falls_through(self):
        sc = SoundCloudAPI()
        resource = {"media": {"transcodings": [
            {"format": {"protocol": "progressive"}},  # no url
            {"url": "https://api/p2",
             "format": {"protocol": "progressive"}},
        ]}}

        def fake_call(endpoint, **kw):
            if "resolve" in endpoint:
                return resource
            return {"url": "u"}

        with patch.object(sc, "_call", side_effect=fake_call):
            assert sc.resolve_stream("https://x") == "u"

    def test_exception_returns_none(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", side_effect=RuntimeError("boom")):
            assert sc.resolve_stream("https://x") is None

    def test_prefers_hq_over_sq_within_same_protocol(self):
        """Regression: resolve_stream must pick the same best-quality
        transcoding that _parse_transcodings/codec+bitrate metadata describes.

        Before the fix, resolve_stream only sorted by protocol match and
        returned the first entry for a given protocol regardless of quality,
        so an "sq" listed before "hq" in the API response would be streamed
        even though the parsed Release metadata (bitrate="256") advertised hq.
        """
        sc = SoundCloudAPI()
        resource = {"media": {"transcodings": [
            {"url": "https://api/sq", "format": {"protocol": "progressive"},
             "quality": "sq"},
            {"url": "https://api/hq", "format": {"protocol": "progressive"},
             "quality": "hq"},
        ]}}

        def fake_call(endpoint, **kw):
            if "resolve" in endpoint:
                return resource
            return {"url": f"stream-for-{endpoint.rsplit('/', 1)[-1]}"}

        with patch.object(sc, "_call", side_effect=fake_call):
            url = sc.resolve_stream("https://x")
        assert url == "stream-for-hq"


# ---------------------------------------------------------------------------
# SoundCloudAPI.resolve_user / resolve_track exception + non-user path
# ---------------------------------------------------------------------------

class TestApiResolveUserTrack:
    def test_resolve_user_non_user_returns_none(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", return_value={"kind": "track"}):
            assert sc.resolve_user("https://x") is None

    def test_resolve_user_exception(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", side_effect=RuntimeError):
            assert sc.resolve_user("https://x") is None

    def test_resolve_track_non_track(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", return_value={"kind": "user"}):
            assert sc.resolve_track("https://x") is None

    def test_resolve_track_exception(self):
        sc = SoundCloudAPI()
        with patch.object(sc, "_call", side_effect=RuntimeError):
            assert sc.resolve_track("https://x") is None


# ---------------------------------------------------------------------------
# SoundCloudAPI download paths — pure-requests, no yt-dlp
# ---------------------------------------------------------------------------

class TestApiDownload:
    def test_safe_filename(self):
        assert SoundCloudAPI._safe_filename("a/b<>c") == "a_b__c"

    def test_download_track_no_stream_raises(self, tmp_path):
        sc = SoundCloudAPI()
        with patch.object(sc, "resolve_stream", return_value=None):
            with pytest.raises(RuntimeError, match="resolve stream"):
                sc.download_track("https://x", output_dir=str(tmp_path))

    def test_download_track_writes_file(self, tmp_path):
        sc = SoundCloudAPI()
        sc.session = MagicMock()
        # Streamed response context manager
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.iter_content.return_value = [b"abc", b"def"]
        cm.raise_for_status.return_value = None
        sc.session.get.return_value = cm

        with patch.object(sc, "resolve_stream", return_value="https://stream"):
            with patch.object(sc, "_call",
                              return_value={"title": "Song",
                                            "user": {"username": "Artist"}}):
                p = sc.download_track("https://x/a/b", output_dir=str(tmp_path))
        assert p.exists()
        assert p.read_bytes() == b"abcdef"
        assert "Artist" in p.name and "Song" in p.name

    def test_download_track_metadata_failure_uses_url_basename(self, tmp_path):
        sc = SoundCloudAPI()
        sc.session = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.iter_content.return_value = [b"x"]
        cm.raise_for_status.return_value = None
        sc.session.get.return_value = cm
        with patch.object(sc, "resolve_stream", return_value="https://s"):
            with patch.object(sc, "_call", side_effect=RuntimeError):
                p = sc.download_track("https://x/a/myslug",
                                      output_dir=str(tmp_path))
        assert "myslug" in p.name

    def test_download_track_artist_in_title_no_double(self, tmp_path):
        sc = SoundCloudAPI()
        sc.session = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.iter_content.return_value = [b"x"]
        cm.raise_for_status.return_value = None
        sc.session.get.return_value = cm
        with patch.object(sc, "resolve_stream", return_value="https://s"):
            with patch.object(sc, "_call",
                              return_value={"title": "Artist - Song",
                                            "user": {"username": "Artist"}}):
                p = sc.download_track("https://x/a/b",
                                      output_dir=str(tmp_path))
        assert p.name == "Artist - Song.mp3"

    def test_download_tracks_handles_failures(self, tmp_path):
        sc = SoundCloudAPI()
        ok = tmp_path / "a.mp3"
        ok.write_bytes(b"x")
        with patch.object(sc, "download_track",
                          side_effect=[RuntimeError("nope"), ok]):
            res = sc.download_tracks(["a", "b"], output_dir=str(tmp_path))
        assert res == [ok]

    def test_download_playlist_empty(self, tmp_path):
        sc = SoundCloudAPI()
        with patch.object(sc, "get_tracks", return_value=iter([])):
            assert sc.download_playlist("https://x",
                                        output_dir=str(tmp_path)) == []

    def test_download_playlist_uses_artist_subdir(self, tmp_path):
        sc = SoundCloudAPI()
        rel = _track_dict_to_release({
            "title": "T", "url": "https://x/a/t",
            "artist": "Mister X", "user_id": 1,
        })
        with patch.object(sc, "get_tracks", return_value=iter([rel])):
            with patch.object(sc, "download_tracks",
                              return_value=[tmp_path / "f.mp3"]) as dt:
                sc.download_playlist("https://x", output_dir=str(tmp_path))
        called_dir = dt.call_args.kwargs["output_dir"]
        assert "Mister X" in called_dir


# ---------------------------------------------------------------------------
# SoundCloudHTML — parser branches
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestHtmlParsers:
    def test_search_tracks_skips_h2_without_anchor(self):
        sc = SoundCloudHTML()
        soup = _soup("<h2><span>nope</span></h2><h2><a href='/a/t'>X</a></h2>")
        with patch.object(sc, "_get_soup", return_value=soup):
            r = list(sc.search_tracks("q", limit=5))
        assert len(r) == 1

    def test_search_people_skips_h2_without_anchor(self):
        sc = SoundCloudHTML()
        soup = _soup("<h2></h2><h2><a href='/u'>U</a></h2>")
        with patch.object(sc, "_get_soup", return_value=soup):
            r = list(sc.search_people("q", limit=5))
        assert len(r) == 1

    def test_search_people_respects_limit(self):
        sc = SoundCloudHTML()
        soup = _soup("".join(f"<h2><a href='/u{i}'>U{i}</a></h2>"
                             for i in range(5)))
        with patch.object(sc, "_get_soup", return_value=soup):
            r = list(sc.search_people("q", limit=2))
        assert len(r) == 2

    def test_search_sets_skips_h2_without_anchor(self):
        sc = SoundCloudHTML()
        soup = _soup("<h2></h2><h2><a href='/a/sets/x'>S</a></h2>")
        with patch.object(sc, "_get_soup", return_value=soup):
            r = list(sc.search_sets("q", limit=5))
        assert len(r) == 1

    def test_search_sets_respects_limit(self):
        sc = SoundCloudHTML()
        soup = _soup("".join(f"<h2><a href='/a/sets/{i}'>{i}</a></h2>"
                             for i in range(5)))
        with patch.object(sc, "_get_soup", return_value=soup):
            r = list(sc.search_sets("q", limit=2))
        assert len(r) == 2

    def test_get_tracks_handles_self_link(self):
        sc = SoundCloudHTML()
        url = "https://soundcloud.com/u"
        html = f"""
        <article itemprop="track">
          <h2 itemprop="name"><a href="{url}">selflink</a></h2>
        </article>
        <article itemprop="track">
          <h2 itemprop="name">
            <a href="/u/t1">Track1</a>
            <a href="/u">Artist</a>
          </h2>
          <meta itemprop="duration" content="PT03M00S">
        </article>
        """
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            r = list(sc.get_tracks(url, limit=5))
        assert len(r) == 1
        assert r[0].work.title == "Track1"
        assert r[0].work.runtime == 180

    def test_get_tracks_skips_articles_without_h2(self):
        sc = SoundCloudHTML()
        html = """
        <article itemprop="track"><span>oops</span></article>
        <article itemprop="track">
          <h2 itemprop="name"><a href="/u/t">T</a></h2>
        </article>
        """
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            r = list(sc.get_tracks("https://soundcloud.com/u", limit=5))
        assert len(r) == 1

    def test_get_tracks_skips_h2_without_links(self):
        sc = SoundCloudHTML()
        html = """
        <article itemprop="track"><h2 itemprop="name">no anchors</h2></article>
        <article itemprop="track">
          <h2 itemprop="name"><a href="/u/t">T</a></h2>
        </article>
        """
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            r = list(sc.get_tracks("https://soundcloud.com/u", limit=5))
        assert len(r) == 1

    def test_get_tracks_respects_limit(self):
        sc = SoundCloudHTML()
        html = "".join(
            f'<article itemprop="track"><h2 itemprop="name">'
            f'<a href="/u/t{i}">T{i}</a></h2></article>'
            for i in range(5)
        )
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            r = list(sc.get_tracks("https://soundcloud.com/u", limit=2))
        assert len(r) == 2

    def test_resolve_user_via_og_title(self):
        sc = SoundCloudHTML()
        html = ('<meta property="og:title" content="Some Artist | SoundCloud">'
                '<meta property="og:image" content="https://img/x.jpg">')
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            ent = sc.resolve_user("https://soundcloud.com/u")
        assert ent.name == "Some Artist"
        assert ent.extra["image"] == "https://img/x.jpg"

    def test_resolve_user_via_jsonld(self):
        sc = SoundCloudHTML()
        html = '<script type="application/ld+json">{"name": "JsonName"}</script>'
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            ent = sc.resolve_user("https://soundcloud.com/u")
        assert ent.name == "JsonName"

    def test_resolve_user_jsonld_garbage(self):
        sc = SoundCloudHTML()
        html = '<script type="application/ld+json">{ broken json</script>'
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            assert sc.resolve_user("https://soundcloud.com/u") is None

    def test_resolve_user_no_data(self):
        sc = SoundCloudHTML()
        with patch.object(sc, "_get_soup", return_value=_soup("<html></html>")):
            assert sc.resolve_user("https://soundcloud.com/u") is None

    def test_resolve_user_exception(self):
        sc = SoundCloudHTML()
        with patch.object(sc, "_get_soup", side_effect=RuntimeError):
            assert sc.resolve_user("https://soundcloud.com/u") is None

    def test_resolve_track_no_meta(self):
        sc = SoundCloudHTML()
        with patch.object(sc, "get_track_meta", return_value={}):
            assert sc.resolve_track("https://x") is None

    def test_resolve_track_exception(self):
        sc = SoundCloudHTML()
        with patch.object(sc, "get_track_meta", side_effect=RuntimeError):
            assert sc.resolve_track("https://x") is None

    def test_resolve_track_happy(self):
        sc = SoundCloudHTML()
        html = '<meta property="og:title" content="Track Title">'
        with patch.object(sc, "get_track_meta",
                          return_value={"artist": "A", "image": "img"}):
            with patch.object(sc, "_get_soup", return_value=_soup(html)):
                rel = sc.resolve_track("https://soundcloud.com/u/t")
        assert rel is not None
        assert rel.image == "img"

    def test_get_track_meta_anchor_fallback(self):
        sc = SoundCloudHTML()
        html = ('<a itemprop="url">FallbackArtist</a>'
                '<meta property="og:image" content="https://img.jpg">')
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            meta = sc.get_track_meta("https://x")
        assert meta["artist"] == "FallbackArtist"
        assert meta["image"] == "https://img.jpg"

    def test_get_track_meta_jsonld_garbage(self):
        sc = SoundCloudHTML()
        html = '<script type="application/ld+json">not json</script>'
        with patch.object(sc, "_get_soup", return_value=_soup(html)):
            meta = sc.get_track_meta("https://x")
        # No artist, no image, but no exception either.
        assert "artist" not in meta or meta.get("artist") is None

    def test_search_tracks_enriched_skips_failure(self):
        sc = SoundCloudHTML()
        # one base release; enrichment errors should not stop iteration
        from mediavocab import (
            MediaType, Release, StreamMode, Work,
        )
        rel = Release(work=Work(title="t", media_type=MediaType.MUSIC),
                      uri="https://x", stream_mode=StreamMode.ON_DEMAND)
        with patch.object(sc, "search_tracks", return_value=iter([rel])):
            with patch.object(sc, "get_track_meta",
                              side_effect=RuntimeError):
                out = list(sc.search_tracks_enriched("q"))
        assert out and out[0].uri == "https://x"

    def test_search_tracks_enriched_adds_image(self):
        sc = SoundCloudHTML()
        from mediavocab import (
            MediaType, Release, StreamMode, Work,
        )
        rel = Release(work=Work(title="t", media_type=MediaType.MUSIC),
                      uri="https://x", stream_mode=StreamMode.ON_DEMAND)
        with patch.object(sc, "search_tracks", return_value=iter([rel])):
            with patch.object(sc, "get_track_meta",
                              return_value={"artist": "A",
                                            "image": "https://img"}):
                out = list(sc.search_tracks_enriched("q"))
        assert out[0].image == "https://img"
        assert out[0].work.credits[0].entity.name == "A"


# ---------------------------------------------------------------------------
# SoundCloudYTDLP — fully mocked
# ---------------------------------------------------------------------------

class FakeYDL:
    def __init__(self, info=None):
        self._info = info or {}
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def extract_info(self, url, download=False):
        return self._info
    def download(self, urls):
        return None


class TestYtdlp:
    def _patch_ydl(self, info):
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(info)
        return patch("nuvem_de_som._ydl_import", return_value=ydl_module)

    def test_search_tracks(self):
        sc = SoundCloudYTDLP()
        info = {"entries": [
            {"id": "1", "title": "T", "url": "u",
             "uploader": "U", "thumbnail": "img", "duration": 60},
            {"id": "bad", "title": "T2", "url": "u2"},  # non-int id branch
        ]}
        with self._patch_ydl(info):
            out = list(sc.search_tracks("q"))
        assert len(out) == 2
        assert out[0].work.runtime == 60

    def test_search_people_returns_empty(self):
        assert list(SoundCloudYTDLP().search_people("q")) == []

    def test_search_sets_returns_empty(self):
        assert list(SoundCloudYTDLP().search_sets("q")) == []

    def test_get_tracks_artist_url(self):
        sc = SoundCloudYTDLP()
        info = {"entries": [{"id": "1", "title": "T", "webpage_url": "u",
                             "channel": "C"}]}
        with self._patch_ydl(info):
            out = list(sc.get_tracks("https://soundcloud.com/u"))
        assert out[0].work.title == "T"

    def test_get_tracks_set_url_blanks_artist(self):
        sc = SoundCloudYTDLP()
        info = {"entries": [{"id": "1", "title": "T",
                             "webpage_url": "u", "uploader": "U"}]}
        with self._patch_ydl(info):
            out = list(sc.get_tracks("https://soundcloud.com/u/sets/x"))
        assert out[0].work.title == "T"

    def test_resolve_stream_progressive(self):
        sc = SoundCloudYTDLP()
        info = {"formats": [
            {"protocol": "m3u8_native", "url": "hls"},
            {"protocol": "https", "url": "prog1"},
            {"protocol": "https", "url": "prog2"},
        ]}
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(info)
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            url = sc.resolve_stream("https://x", prefer="progressive")
        assert url == "prog2"

    def test_resolve_stream_hls(self):
        sc = SoundCloudYTDLP()
        info = {"formats": [
            {"protocol": "https", "url": "p"},
            {"protocol": "m3u8_native", "url": "hls"},
        ]}
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(info)
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            url = sc.resolve_stream("https://x", prefer="hls")
        assert url == "hls"

    def test_resolve_stream_falls_back_to_last(self):
        sc = SoundCloudYTDLP()
        info = {"formats": [{"protocol": "other", "url": "only"}]}
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(info)
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            url = sc.resolve_stream("https://x")
        assert url == "only"

    def test_resolve_stream_url_field(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(
            {"formats": [], "url": "fallback"})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.resolve_stream("https://x") == "fallback"

    def test_resolve_stream_exception_returns_none(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.side_effect = RuntimeError
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.resolve_stream("https://x") is None

    def test_resolve_stream_propagates_import_error(self):
        sc = SoundCloudYTDLP()
        with patch("nuvem_de_som._ydl_import",
                   side_effect=ImportError("no yt-dlp")):
            with pytest.raises(ImportError):
                sc.resolve_stream("https://x")

    def test_resolve_user(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(
            {"uploader": "U", "thumbnail": "img", "uploader_id": "1"})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            ent = sc.resolve_user("https://soundcloud.com/u")
        assert ent.name == "U"

    def test_resolve_user_empty(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL({})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.resolve_user("https://x") is None

    def test_resolve_user_exception_returns_none(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.side_effect = RuntimeError
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.resolve_user("https://x") is None

    def test_resolve_user_propagates_import_error(self):
        sc = SoundCloudYTDLP()
        with patch("nuvem_de_som._ydl_import", side_effect=ImportError):
            with pytest.raises(ImportError):
                sc.resolve_user("https://x")

    def test_resolve_track(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(
            {"id": "5", "title": "T", "webpage_url": "u", "uploader": "U"})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            rel = sc.resolve_track("https://x")
        assert rel.work.title == "T"

    def test_resolve_track_non_int_id(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL(
            {"id": "abc", "title": "T", "webpage_url": "u", "uploader": "U"})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            rel = sc.resolve_track("https://x")
        assert rel.work.title == "T"

    def test_resolve_track_exception(self):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.side_effect = RuntimeError
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.resolve_track("https://x") is None

    def test_resolve_track_propagates_import_error(self):
        sc = SoundCloudYTDLP()
        with patch("nuvem_de_som._ydl_import", side_effect=ImportError):
            with pytest.raises(ImportError):
                sc.resolve_track("https://x")

    def test_download_track_returns_path(self, tmp_path):
        sc = SoundCloudYTDLP()
        captured_opts = {}

        class CapturingYDL(FakeYDL):
            def __init__(self, opts):
                captured_opts.update(opts)
                super().__init__({})
            def download(self, urls):
                # invoke progress hook to populate downloaded list
                hook = captured_opts["progress_hooks"][0]
                hook({"status": "finished",
                      "filename": str(tmp_path / "file.mp3")})

        ydl_module = MagicMock()
        ydl_module.YoutubeDL.side_effect = lambda opts: CapturingYDL(opts)
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            p = sc.download_track("https://x", output_dir=str(tmp_path),
                                  verbose=True)
        assert p == Path(tmp_path / "file.mp3")

    def test_download_track_returns_none_when_no_finish(self, tmp_path):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()
        ydl_module.YoutubeDL.return_value = FakeYDL({})
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            assert sc.download_track("https://x",
                                     output_dir=str(tmp_path)) is None

    def test_download_tracks_filters_none(self, tmp_path):
        sc = SoundCloudYTDLP()
        with patch.object(sc, "download_track",
                          side_effect=[None, Path("/tmp/x.mp3")]):
            res = sc.download_tracks(["a", "b"], output_dir=str(tmp_path))
        assert res == [Path("/tmp/x.mp3")]

    def test_download_playlist(self, tmp_path):
        sc = SoundCloudYTDLP()
        ydl_module = MagicMock()

        class CapturingYDL(FakeYDL):
            def __init__(self, opts):
                self.opts = opts
                super().__init__({})
            def download(self, urls):
                hook = self.opts["progress_hooks"][0]
                hook({"status": "finished",
                      "filename": str(tmp_path / "Artist" / "song.mp3")})

        ydl_module.YoutubeDL.side_effect = lambda opts: CapturingYDL(opts)
        with patch("nuvem_de_som._ydl_import", return_value=ydl_module):
            res = sc.download_playlist("https://x", output_dir=str(tmp_path))
        assert res and res[0].name == "song.mp3"


# ---------------------------------------------------------------------------
# SoundCloud orchestrator — additional fallback paths
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def test_resolve_user_falls_through(self):
        sc = SoundCloud()
        with patch.object(sc._chain[0], "resolve_user", return_value=None):
            with patch.object(sc._chain[1], "resolve_user", return_value=None):
                with patch.object(sc._chain[2], "resolve_user",
                                  return_value="X"):
                    assert sc.resolve_user("u") == "X"

    def test_resolve_user_swallows_exceptions(self):
        sc = SoundCloud()
        with patch.object(sc._chain[0], "resolve_user",
                          side_effect=RuntimeError):
            with patch.object(sc._chain[1], "resolve_user",
                              return_value="X"):
                assert sc.resolve_user("u") == "X"

    def test_resolve_track_falls_through(self):
        sc = SoundCloud()
        with patch.object(sc._chain[0], "resolve_track", return_value=None):
            with patch.object(sc._chain[1], "resolve_track",
                              return_value="R"):
                assert sc.resolve_track("u") == "R"

    def test_resolve_track_returns_none_when_all_fail(self):
        sc = SoundCloud()
        for b in sc._chain:
            patch.object(b, "resolve_track",
                         side_effect=RuntimeError).start()
        try:
            assert sc.resolve_track("u") is None
        finally:
            patch.stopall()

    def test_search_methods_yield(self):
        sc = SoundCloud()
        with patch.object(sc._chain[0], "search_people",
                          return_value=iter([{"x": 1}])):
            assert list(sc.search_people("q")) == [{"x": 1}]
        with patch.object(sc._chain[0], "search_sets",
                          return_value=iter([{"x": 2}])):
            assert list(sc.search_sets("q")) == [{"x": 2}]
        with patch.object(sc._chain[0], "get_tracks",
                          return_value=iter([{"x": 3}])):
            assert list(sc.get_tracks("u")) == [{"x": 3}]

    def test_resolve_stream_validates_prefer(self):
        sc = SoundCloud()
        with pytest.raises(ValueError):
            sc.resolve_stream("u", prefer="bad")

    def test_download_track_falls_back_to_ytdlp(self, tmp_path):
        sc = SoundCloud()
        with patch.object(sc._api, "download_track",
                          side_effect=RuntimeError):
            with patch.object(sc._ytdlp, "download_track",
                              return_value=Path("/tmp/x.mp3")) as ydlp:
                p = sc.download_track("https://x",
                                      output_dir=str(tmp_path))
        assert p == Path("/tmp/x.mp3")
        ydlp.assert_called_once()

    def test_download_track_api_succeeds(self, tmp_path):
        sc = SoundCloud()
        with patch.object(sc._api, "download_track",
                          return_value=Path("/tmp/y.mp3")):
            p = sc.download_track("https://x", output_dir=str(tmp_path))
        assert p == Path("/tmp/y.mp3")

    def test_download_tracks_filters_none(self, tmp_path):
        sc = SoundCloud()
        with patch.object(sc, "download_track",
                          side_effect=[None, Path("/tmp/y.mp3")]):
            assert sc.download_tracks(["a", "b"],
                                      output_dir=str(tmp_path)) == [
                Path("/tmp/y.mp3")
            ]

    def test_download_playlist_falls_back(self, tmp_path):
        sc = SoundCloud()
        with patch.object(sc._api, "download_playlist",
                          side_effect=RuntimeError):
            with patch.object(sc._ytdlp, "download_playlist",
                              return_value=[Path("/tmp/x.mp3")]) as ydlp:
                res = sc.download_playlist("https://x",
                                           output_dir=str(tmp_path))
        assert res == [Path("/tmp/x.mp3")]
        ydlp.assert_called_once()

    def test_download_playlist_api_succeeds(self, tmp_path):
        sc = SoundCloud()
        with patch.object(sc._api, "download_playlist",
                          return_value=[Path("/tmp/x.mp3")]):
            res = sc.download_playlist("https://x",
                                       output_dir=str(tmp_path))
        assert res == [Path("/tmp/x.mp3")]

    def test_api_property_missing_raises(self):
        sc = SoundCloud()
        sc._chain = [SoundCloudHTML()]
        with pytest.raises(RuntimeError, match="SoundCloudAPI"):
            _ = sc._api

    def test_ytdlp_property_missing_raises(self):
        sc = SoundCloud()
        sc._chain = [SoundCloudHTML()]
        with pytest.raises(RuntimeError, match="SoundCloudYTDLP"):
            _ = sc._ytdlp


# ---------------------------------------------------------------------------
# search() method on the abstract base — uses search_people/sets/tracks
# ---------------------------------------------------------------------------

class TestSearchBase:
    def test_search_walks_people_sets_tracks(self):
        sc = SoundCloudAPI()

        from mediavocab import (
            Entity, EntityKind, MediaType, Release, StreamMode, Work,
        )
        person = Entity(name="P", kind=EntityKind.PERSON,
                        extra={"artist_url": "https://soundcloud.com/p"})
        rel = Release(work=Work(title="T", media_type=MediaType.MUSIC),
                      uri="https://soundcloud.com/p/sets/s",
                      stream_mode=StreamMode.ON_DEMAND)
        track_rel = Release(work=Work(title="X", media_type=MediaType.MUSIC),
                            uri="https://soundcloud.com/x",
                            stream_mode=StreamMode.ON_DEMAND)

        with patch.object(sc, "search_people", return_value=iter([person])):
            with patch.object(sc, "search_sets", return_value=iter([rel])):
                with patch.object(sc, "get_tracks",
                                  return_value=iter([track_rel])):
                    with patch.object(sc, "search_tracks",
                                      return_value=iter([track_rel])):
                        out = list(sc.search("q"))
        assert track_rel in out
