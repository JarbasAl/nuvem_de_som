"""Unit tests for SoundCloudAPI.crawl() and SoundCloudBase.crawl().

All tests are offline — no network IO.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mediavocab import Entity, EntityKind

from nuvem_de_som import SoundCloudAPI, SoundCloudHTML


def _entity(name: str, url: str) -> Entity:
    return Entity(
        name=name,
        kind=EntityKind.PERSON,
        extra={"artist_url": url, "image": ""},
    )


class TestApiCrawl:
    def test_crawl_yields_entity(self):
        sc = SoundCloudAPI()
        ent = _entity("Noisia", "https://soundcloud.com/noisia")
        with patch.object(sc, "resolve_user", return_value=ent):
            with patch.object(sc, "get_followers", return_value=iter([])):
                with patch.object(sc, "get_following", return_value=iter([])):
                    out = list(sc.crawl(["https://soundcloud.com/noisia"]))
        assert len(out) == 1
        assert out[0].name == "Noisia"

    def test_crawl_max_artists(self):
        sc = SoundCloudAPI()

        def make_entity(url):
            name = url.rstrip("/").split("/")[-1]
            return _entity(name, url)

        seeds = [
            "https://soundcloud.com/a",
            "https://soundcloud.com/b",
            "https://soundcloud.com/c",
        ]
        with patch.object(sc, "resolve_user", side_effect=make_entity):
            with patch.object(sc, "get_followers", return_value=iter([])):
                with patch.object(sc, "get_following", return_value=iter([])):
                    out = list(sc.crawl(seeds, max_artists=2))
        assert len(out) == 2

    def test_crawl_seen_set_prevents_revisit(self):
        sc = SoundCloudAPI()
        url = "https://soundcloud.com/noisia"
        seen = {url}
        with patch.object(sc, "resolve_user") as ru:
            out = list(sc.crawl([url], seen=seen))
        assert out == []
        ru.assert_not_called()

    def test_crawl_query_seed_uses_search_people(self):
        sc = SoundCloudAPI()
        ent = _entity("Some Band", "https://soundcloud.com/someband")
        resolved = _entity("Some Band", "https://soundcloud.com/someband")
        with patch.object(sc, "search_people", return_value=iter([ent])) as sp:
            with patch.object(sc, "resolve_user", return_value=resolved):
                with patch.object(sc, "get_followers", return_value=iter([])):
                    with patch.object(sc, "get_following", return_value=iter([])):
                        out = list(sc.crawl(["some band query"]))
        sp.assert_called_once_with("some band query", limit=1)
        assert len(out) == 1

    def test_crawl_expands_social_graph(self):
        sc = SoundCloudAPI()
        seed_url = "https://soundcloud.com/noisia"
        follower_url = "https://soundcloud.com/follower1"

        seed_ent = _entity("Noisia", seed_url)
        follower_ent = _entity("Follower1", follower_url)
        follower_resolved = _entity("Follower1", follower_url)

        resolve_calls = {seed_url: seed_ent, follower_url: follower_resolved}

        with patch.object(sc, "resolve_user", side_effect=lambda u: resolve_calls.get(u)):
            with patch.object(sc, "get_followers", return_value=iter([follower_ent])):
                with patch.object(sc, "get_following", return_value=iter([])):
                    out = list(sc.crawl([seed_url]))

        assert any(e.name == "Follower1" for e in out)


class TestBaseCrawl:
    def test_base_crawl_url_seed_resolves(self):
        sc = SoundCloudHTML()
        url = "https://soundcloud.com/noisia"
        ent = _entity("Noisia", url)
        with patch.object(sc, "resolve_user", return_value=ent):
            out = list(sc.crawl([url]))
        assert len(out) == 1
        assert out[0].name == "Noisia"

    def test_base_crawl_query_seed_uses_search_people(self):
        sc = SoundCloudHTML()
        ent = _entity("Metal Band", "https://soundcloud.com/metalband")
        with patch.object(sc, "search_people", return_value=iter([ent])) as sp:
            out = list(sc.crawl(["metal band"]))
        sp.assert_called_once()
        assert len(out) == 1

    def test_base_crawl_seen_prevents_revisit(self):
        sc = SoundCloudHTML()
        url = "https://soundcloud.com/noisia"
        ent = _entity("Noisia", url)
        with patch.object(sc, "resolve_user", return_value=ent):
            out = list(sc.crawl([url], seen={url}))
        assert out == []

    def test_base_crawl_max_artists(self):
        sc = SoundCloudHTML()
        urls = [
            "https://soundcloud.com/a",
            "https://soundcloud.com/b",
            "https://soundcloud.com/c",
        ]
        def make_entity(url):
            return _entity(url.split("/")[-1], url)
        with patch.object(sc, "resolve_user", side_effect=make_entity):
            out = list(sc.crawl(urls, max_artists=2))
        assert len(out) == 2
