"""nuvem_de_som — SoundCloud search, stream, and download client.

Three independent concrete backends, one orchestrator:

- ``SoundCloudAPI``    — SoundCloud internal API v2.  Full metadata in one call.
                         Requires only ``requests``.  Recommended.
- ``SoundCloudHTML``   — HTML page scraper.  No API key, ~20 results per page.
                         No extra deps.
- ``SoundCloudYTDLP``  — yt-dlp backed.  Best stream resolution; slower search.
                         Requires ``pip install nuvem_de_som[yt-dlp]``.
                         Download methods (``download_track``, ``download_tracks``,
                         ``download_playlist``) are only available on this backend
                         and on the ``SoundCloud`` orchestrator.
- ``SoundCloud``       — Orchestrator.  Tries API → yt-dlp → HTML, falls back
                         transparently on errors.  Download methods delegate to
                         the yt-dlp backend.  Use concrete classes directly when
                         you need a specific backend.

Quick start::

    from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP

    sc = SoundCloud()        # orchestrator: API → yt-dlp → HTML
    sc = SoundCloudAPI()     # API only (recommended)
    sc = SoundCloudHTML()    # HTML scraper only
    sc = SoundCloudYTDLP()   # yt-dlp only

    for t in sc.search_tracks("nuclear chill", limit=5):
        # t is a mediavocab.Release; t.work is a mediavocab.Work
        print(t.work.title, t.work.credits[0].entity.name if t.work.credits else "")

    # SoundCloudAPI.download_* uses only requests (no yt-dlp).
    # SoundCloudYTDLP.download_* uses yt-dlp (pip install nuvem_de_som[yt-dlp]).
    # SoundCloud orchestrator tries API first, falls back to yt-dlp.
    sc = SoundCloudAPI()
    sc.download_track("https://soundcloud.com/user/track", output_dir="~/Music")
    sc.download_playlist("https://soundcloud.com/user", output_dir="~/Music")

All track methods return ``mediavocab.Release`` objects::

    release.uri          # SoundCloud permalink
    release.image        # artwork URL
    release.work.title   # track title
    release.work.runtime # duration in seconds (float or None)
    release.work.credits[0].entity.name  # artist display name
    release.work.external_ids["soundcloud_track_id"]
    release.work.external_ids["soundcloud_user_id"]

People/user methods return ``mediavocab.Entity`` objects::

    entity.name          # display name
    entity.extra["artist_url"]
    entity.extra["image"]
    entity.external_ids["soundcloud_user_id"]
"""

from __future__ import annotations

import logging
import re
import threading
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

import requests
from bs4 import BeautifulSoup

from nuvem_de_som.transport import default_session

from mediavocab import (
    Appearance,
    Entity, EntityRef, EntityKind,
    Credit, CreditSection, RelationRole,
    Release, Work, MediaType, StreamMode,
)
from mediavocab.taxonomy import genre as _genre_tax

log = logging.getLogger(__name__)

_PREFER_VALUES = frozenset(("progressive", "hls"))

# SoundCloud `license` field → SPDX identifier.
# `all-rights-reserved` has no SPDX equivalent; we leave it as the raw string
# so consumers can still distinguish it from "unknown".
_SC_LICENSE_TO_SPDX = {
    "no-rights-reserved": "CC0-1.0",
    "cc-by": "CC-BY-4.0",
    "cc-by-nc": "CC-BY-NC-4.0",
    "cc-by-nd": "CC-BY-ND-4.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "cc-by-nc-nd": "CC-BY-NC-ND-4.0",
    "cc-by-nc-sa": "CC-BY-NC-SA-4.0",
}


def _map_license(value: str | None) -> str:
    """Map a SoundCloud `license` value to an SPDX id (or pass through)."""
    if not value:
        return ""
    return _SC_LICENSE_TO_SPDX.get(value, value)


def _build_genres(genre: str | None, tag_list: str | None) -> list[str]:
    """Return content_genres from SC `genre` + free-form `tag_list`.

    Recognised tokens are mapped to ``mediavocab.taxonomy.genre.GENRE_*``
    constants; unrecognised tokens are preserved as free strings.
    SoundCloud `tag_list` separates tags by spaces but supports
    quoted multi-word tags (``"drum and bass"``).
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        if not raw:
            return
        token = raw.strip().strip('"').lower()
        if not token:
            return
        # Try to resolve to a canonical GENRE_* constant.
        candidates = [
            token,
            token.replace(" ", "_").replace("-", "_"),
            token.replace("&", "and").replace(" ", "_"),
        ]
        mapped: str | None = None
        for c in candidates:
            attr = "GENRE_" + c.upper()
            value = getattr(_genre_tax, attr, None)
            if isinstance(value, str):
                mapped = value
                break
        final = mapped or token
        if final not in seen:
            seen.add(final)
            out.append(final)

    if genre:
        _add(genre)
    if tag_list:
        # SC tag_list: space-separated, quoted multi-word tags.
        tokens = re.findall(r'"([^"]+)"|(\S+)', tag_list)
        for q, w in tokens:
            _add(q or w)
    return out


def _parse_transcodings(transcodings: list[dict]) -> tuple[str, str]:
    """Return ``(codec, bitrate)`` derived from SC transcoding entries.

    SoundCloud encodes ``mime_type`` (e.g. ``audio/mpeg``, ``audio/ogg``)
    and ``quality`` (``sq`` ≈ 128 kbps, ``hq`` ≈ 256 kbps). We pick the
    highest-quality progressive entry available.
    """
    if not transcodings:
        return "", ""
    # Prefer progressive protocol so codec/bitrate describe the directly
    # playable stream rather than an HLS variant.
    progressive = [
        t for t in transcodings
        if ((t.get("format") or {}).get("protocol") or "").lower() == "progressive"
    ]
    pool = progressive or transcodings
    # Within the pool, prefer hq, then sq, then anything.
    rank = {"hq": 0, "sq": 1}
    ordered = sorted(pool,
                     key=lambda t: rank.get((t.get("quality") or "").lower(), 9))
    best = ordered[0]
    fmt = best.get("format") or {}
    codec = fmt.get("mime_type") or ""
    quality = (best.get("quality") or "").lower()
    bitrate = {"hq": "256", "sq": "128"}.get(quality, "")
    return codec, bitrate

# ---------------------------------------------------------------------------
# client_id management — pure requests, no yt-dlp
# ---------------------------------------------------------------------------

_CLIENT_ID: str | None = None
_CLIENT_ID_LOCK = threading.Lock()

_CLIENT_ID_PATTERNS = [
    r'"client_id"\s*:\s*"([0-9a-zA-Z]{32})"',
    r"client_id\s*:\s*\"([0-9a-zA-Z]{32})\"",
    r"client_id=([0-9a-zA-Z]{32})",
]

_SC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    )
}


def _fetch_client_id(session=None) -> str:
    """Extract SoundCloud API client_id from their bundled JS files."""
    s = session if session is not None else requests
    try:
        resp = s.get("https://soundcloud.com/", timeout=10, headers=_SC_HEADERS)
        resp.raise_for_status()
    except RuntimeError as exc:
        # unblock_requests.CloudflareSession raises RuntimeError instead of
        # returning a Response when a GET is served a Cloudflare challenge it
        # can't clear. There is no client_id to invalidate/retry here (this is
        # the bootstrap fetch _call's 401/403 refresh loop depends on), so
        # surface it as the same failure mode as a JS-bundle parse miss.
        raise RuntimeError(
            f"Could not extract SoundCloud client_id from JS bundles: {exc}"
        ) from exc
    script_urls = re.findall(r'<script[^>]+src="(https://[^"]+\.js[^"]*)"', resp.text)
    for src in reversed(script_urls):  # last bundles contain app config
        try:
            js = s.get(src, timeout=10).text
            for pat in _CLIENT_ID_PATTERNS:
                m = re.search(pat, js)
                if m:
                    return m.group(1)
        except requests.RequestException as exc:
            log.debug("Failed to fetch JS bundle %s: %s", src, exc)
            continue
    raise RuntimeError("Could not extract SoundCloud client_id from JS bundles")


def _get_client_id(session=None) -> str:
    global _CLIENT_ID
    with _CLIENT_ID_LOCK:
        if not _CLIENT_ID:
            _CLIENT_ID = _fetch_client_id(session=session)
        return _CLIENT_ID


def _invalidate_client_id() -> None:
    global _CLIENT_ID
    with _CLIENT_ID_LOCK:
        _CLIENT_ID = None


def _ydl_import():
    try:
        import yt_dlp  # noqa: PLC0415
        return yt_dlp
    except ImportError as e:
        raise ImportError(
            "yt-dlp is required for downloads; "
            "install with: pip install nuvem_de_som[yt-dlp]"
        ) from e


def _empty_track(url: str = "") -> dict:
    """Return an empty track dict with the canonical key set."""
    return {"title": "", "url": url, "artist": "", "artist_url": "", "image": "",
            "duration": None}


_AUDIO_CHANNELS_STEREO = "stereo"


def _track_dict_to_release(d: dict) -> Release:
    """Convert an internal track dict to a mediavocab Release.

    The dict may include the optional enrichment keys:
    ``permalink`` (slug → ``Work.aka``), ``content_genres`` (list[str]),
    ``license`` (mapped SPDX), ``release_date`` (ISO 8601), ``codec``,
    ``bitrate``, ``audio_channels``, and ``country`` on the uploader.
    Unknown keys are ignored.
    """
    external_ids: dict[str, str] = {}
    if d.get("track_id") is not None:
        external_ids["soundcloud_track_id"] = str(d["track_id"])
    if d.get("user_id") is not None:
        external_ids["soundcloud_user_id"] = str(d["user_id"])

    credits: list[Credit] = []
    if d.get("artist"):
        artist_ref = EntityRef(
            name=d["artist"],
            kind=EntityKind.PERSON,
            external_ids=({"soundcloud_user_id": str(d["user_id"])}
                          if d.get("user_id") is not None else {}),
        )
        credits.append(Credit(
            entity=artist_ref,
            role="artist",
            relation_role=RelationRole.PERFORMER,
            section=CreditSection.PRINCIPAL,
        ))

    work = Work(
        title=d.get("title") or "",
        media_type=MediaType.MUSIC,
        runtime=float(d["duration"]) if d.get("duration") is not None else None,
        credits=credits,
        content_genres=list(d.get("content_genres") or []),
        country=d.get("country") or "",
        aka=[d["permalink"]] if d.get("permalink") else [],
        external_ids=external_ids,
        extra=({"artist_url": d["artist_url"]} if d.get("artist_url") else {}),
    )
    return Release(
        work=work,
        uri=d.get("url") or "",
        image=d.get("image") or "",
        stream_mode=StreamMode.ON_DEMAND,
        codec=d.get("codec") or "",
        bitrate=d.get("bitrate") or "",
        audio_channels=d.get("audio_channels") or "",
        license=d.get("license") or "",
        release_date=d.get("release_date") or None,
        external_ids=external_ids,
    )


def _user_dict_to_entity(d: dict) -> Entity:
    """Convert an internal user/artist dict to a mediavocab Entity.

    Optional keys: ``country`` (ISO 3166 alpha-2 from SoundCloud
    ``country_code``) and ``permalink`` (URL slug, surfaced via
    ``extra.permalink``).
    """
    external_ids: dict[str, str] = {}
    if d.get("user_id") is not None:
        external_ids["soundcloud_user_id"] = str(d["user_id"])
    extra: dict[str, str] = {"image": d.get("image") or ""}
    if d.get("artist_url"):
        extra["artist_url"] = d["artist_url"]
    if d.get("country"):
        extra["country"] = d["country"]
    if d.get("permalink"):
        extra["permalink"] = d["permalink"]
    return Entity(
        name=d.get("artist") or "",
        kind=EntityKind.PERSON,
        external_ids=external_ids,
        extra=extra,
    )


def _set_dict_to_release(d: dict) -> Release:
    """Convert an internal playlist/set dict to a mediavocab Release.

    Optional ``tracks`` (list of internal track dicts) is converted to a
    typed ``Work.tracklist`` of :class:`mediavocab.Appearance` entries.
    """
    external_ids: dict[str, str] = {}
    if d.get("playlist_id") is not None:
        external_ids["soundcloud_playlist_id"] = str(d["playlist_id"])
    if d.get("user_id") is not None:
        external_ids["soundcloud_user_id"] = str(d["user_id"])

    credits: list[Credit] = []
    if d.get("artist"):
        artist_ref = EntityRef(
            name=d["artist"],
            kind=EntityKind.PERSON,
            external_ids=({"soundcloud_user_id": str(d["user_id"])}
                          if d.get("user_id") is not None else {}),
        )
        credits.append(Credit(
            entity=artist_ref,
            role="artist",
            relation_role=RelationRole.CREATOR,
            section=CreditSection.PRINCIPAL,
        ))

    tracklist: list[Appearance] = []
    for i, t in enumerate(d.get("tracks") or [], start=1):
        if not t.get("title"):
            continue
        track_release = _track_dict_to_release(t)
        tracklist.append(Appearance(work=track_release.work, position=i))

    work = Work(
        title=d.get("title") or "",
        media_type=MediaType.MUSIC,
        credits=credits,
        content_genres=list(d.get("content_genres") or []),
        aka=[d["permalink"]] if d.get("permalink") else [],
        tracklist=tracklist,
        external_ids=external_ids,
        extra=({"artist_url": d["artist_url"]} if d.get("artist_url") else {}),
    )
    return Release(
        work=work,
        uri=d.get("url") or "",
        image=d.get("image") or "",
        stream_mode=StreamMode.ON_DEMAND,
        license=d.get("license") or "",
        release_date=d.get("release_date") or None,
        external_ids=external_ids,
    )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class SoundCloudBase(ABC):
    """Abstract interface — one class per backend, all methods required.

    All public methods return mediavocab objects:
    - track methods yield ``Release`` (with ``Work`` embedded)
    - people/user methods yield or return ``Entity``
    - set methods yield ``Release``
    """

    # -- required ------------------------------------------------------------

    @abstractmethod
    def search_tracks(self, query: str, limit: int = 10) -> Iterator[Release]:
        """Yield Release objects matching *query*."""

    @abstractmethod
    def search_people(self, query: str, limit: int = 10) -> Iterator[Entity]:
        """Yield Entity objects matching *query*."""

    @abstractmethod
    def search_sets(self, query: str, limit: int = 10) -> Iterator[Release]:
        """Yield Release objects for playlists/sets matching *query*."""

    @abstractmethod
    def get_tracks(self, url: str, limit: int = 200) -> Iterator[Release]:
        """Yield Release objects for an artist profile or set URL."""

    @abstractmethod
    def resolve_stream(self, track_url: str, prefer: str = "progressive") -> str | None:
        """Resolve a SoundCloud track URL to a direct audio stream URL.

        Parameters
        ----------
        track_url:
            SoundCloud track permalink.
        prefer:
            ``"progressive"`` (direct MP3/AAC, seekable) or ``"hls"`` (m3u8).

        Returns the stream URL string, or ``None`` when not resolvable.
        """

    @abstractmethod
    def resolve_user(self, profile_url: str) -> Entity | None:
        """Resolve a profile URL to an Entity, or ``None``."""

    @abstractmethod
    def resolve_track(self, track_url: str) -> Release | None:
        """Resolve a track permalink URL to a Release, or ``None``."""

    # -- concrete shared -----------------------------------------------------

    def search(self, query: str, limit: int = 10) -> Iterator[Release]:
        """Combined search: artist tracks + set tracks + direct track search."""
        for person in self.search_people(query, limit=3):
            url = person.extra.get("artist_url") or ""
            if url:
                yield from self.get_tracks(url, limit=5)
        for pl in self.search_sets(query, limit=3):
            url = pl.uri or ""
            if url:
                yield from self.get_tracks(url, limit=5)
        yield from self.search_tracks(query, limit=limit)


# ---------------------------------------------------------------------------
# Backend 1: SoundCloud API v2
# ---------------------------------------------------------------------------

class SoundCloudAPI(SoundCloudBase):
    """SoundCloud internal API v2 backend.

    Full metadata (display name, artwork, duration) in a single call per query.
    Requires only ``requests`` — no yt-dlp for search, listing, or stream
    resolution.  Stream resolution uses the transcodings endpoint natively.

    Pass ``session=`` to inject a custom HTTP session (e.g. ``curl_cffi``
    for browser impersonation).  Defaults to :func:`transport.default_session`.
    """

    def __init__(self, session=None):
        self.session = session if session is not None else default_session()

    def _call(self, endpoint: str, **params) -> dict:
        """Call an API v2 endpoint; refresh client_id automatically on 401/403."""
        for attempt in range(2):
            cid = _get_client_id(session=self.session)
            try:
                resp = self.session.get(
                    endpoint,
                    params={"client_id": cid, **params},
                    timeout=10,
                    headers=_SC_HEADERS,
                )
            except RuntimeError as exc:
                # unblock_requests.CloudflareSession raises RuntimeError
                # instead of returning a Response when a GET is served a
                # Cloudflare challenge it can't clear on its own. We can't
                # tell from the exception alone whether that challenge was
                # triggered by a stale client_id, but refreshing it is a
                # cheap, safe thing to try before giving up — it is exactly
                # what the 401/403 branch below already does for a rejected
                # id, so treat "challenge served" the same way once.
                if attempt == 0:
                    log.debug("challenge served (%s), refreshing client_id", exc)
                    _invalidate_client_id()
                    continue
                raise
            if resp.status_code in (401, 403) and attempt == 0:
                log.debug("client_id rejected (%s), refreshing", resp.status_code)
                _invalidate_client_id()
                continue
            resp.raise_for_status()
            return resp.json()
        # unreachable: the loop always returns or raises above
        raise RuntimeError("unexpected exit from _call retry loop")

    @staticmethod
    def _parse_track(t: dict, artist_url: str | None = None) -> dict:
        user = t.get("user") or {}
        image = t.get("artwork_url") or user.get("avatar_url") or ""
        duration = (t["duration"] // 1000) if t.get("duration") else None
        codec, bitrate = _parse_transcodings(
            ((t.get("media") or {}).get("transcodings") or [])
        )
        # SoundCloud release dates are ISO 8601 (e.g. ``2018-09-25T15:36:31Z``).
        # Take the date prefix only — Release.release_date is validated as IsoDate.
        created_at = t.get("display_date") or t.get("created_at") or ""
        release_date = created_at[:10] if len(created_at) >= 10 else None
        return {
            "title": t.get("title") or "",
            "url": t.get("permalink_url") or "",
            "artist": user.get("username") or "",
            "artist_url": artist_url or user.get("permalink_url") or "",
            "image": image,
            "duration": duration,
            "track_id": t.get("id"),
            "user_id": user.get("id"),
            "permalink": t.get("permalink") or "",
            "content_genres": _build_genres(t.get("genre"), t.get("tag_list")),
            "license": _map_license(t.get("license")),
            "release_date": release_date,
            "codec": codec,
            "bitrate": bitrate,
            "audio_channels": _AUDIO_CHANNELS_STEREO if codec else "",
            "country": (user.get("country_code") or "") if user else "",
        }

    def search_tracks(self, query: str, limit: int = 10) -> Iterator[Release]:
        data = self._call(
            "https://api-v2.soundcloud.com/search/tracks", q=query, limit=limit
        )
        for t in data.get("collection") or []:
            yield _track_dict_to_release(self._parse_track(t))

    def search_people(self, query: str, limit: int = 10) -> Iterator[Entity]:
        data = self._call(
            "https://api-v2.soundcloud.com/search/users", q=query, limit=limit
        )
        for u in data.get("collection") or []:
            yield _user_dict_to_entity({
                "artist": u.get("username") or "",
                "artist_url": u.get("permalink_url") or "",
                "image": u.get("avatar_url") or "",
                "user_id": u.get("id"),
                "country": u.get("country_code") or "",
                "permalink": u.get("permalink") or "",
            })

    def search_sets(self, query: str, limit: int = 10) -> Iterator[Release]:
        data = self._call(
            "https://api-v2.soundcloud.com/search/playlists", q=query, limit=limit
        )
        for p in data.get("collection") or []:
            user = p.get("user") or {}
            tracks_raw = p.get("tracks") or []
            artist_url = user.get("permalink_url") or ""
            tracks_parsed = [
                self._parse_track(t, artist_url=artist_url)
                for t in tracks_raw if t.get("title")
            ]
            created = p.get("display_date") or p.get("created_at") or ""
            yield _set_dict_to_release({
                "title": p.get("title") or "",
                "url": p.get("permalink_url") or "",
                "artist": user.get("username") or "",
                "artist_url": artist_url,
                "image": p.get("artwork_url") or user.get("avatar_url") or "",
                "playlist_id": p.get("id"),
                "user_id": user.get("id"),
                "permalink": p.get("permalink") or "",
                "content_genres": _build_genres(p.get("genre"), p.get("tag_list")),
                "license": _map_license(p.get("license")),
                "release_date": created[:10] if len(created) >= 10 else None,
                "tracks": tracks_parsed,
            })

    def get_tracks(self, url: str, limit: int = 200) -> Iterator[Release]:
        resource = self._call("https://api-v2.soundcloud.com/resolve", url=url)
        kind = resource.get("kind")
        collected = 0

        if kind == "user":
            user_id = resource["id"]
            artist_url = resource.get("permalink_url") or url
            next_href = f"https://api-v2.soundcloud.com/users/{user_id}/tracks"
            while next_href and collected < limit:
                page_size = min(50, limit - collected)
                page = self._call(next_href, limit=page_size, linked_partitioning=1)
                for t in page.get("collection") or []:
                    if collected >= limit:
                        return
                    yield _track_dict_to_release(self._parse_track(t, artist_url=artist_url))
                    collected += 1
                next_href = page.get("next_href")

        elif kind == "playlist":
            artist_url = (resource.get("user") or {}).get("permalink_url") or ""
            for t in resource.get("tracks") or []:
                if collected >= limit:
                    return
                if not t.get("title"):
                    log.debug("get_tracks: skipping untitled track in playlist %s", url)
                    continue
                yield _track_dict_to_release(self._parse_track(t, artist_url=artist_url))
                collected += 1

        else:
            log.debug("get_tracks: unexpected resource kind %r for %s", kind, url)

    def resolve_stream(self, track_url: str, prefer: str = "progressive") -> str | None:
        """Resolve track URL to a direct audio stream via transcodings — no yt-dlp.

        Parameters
        ----------
        prefer:
            ``"progressive"`` (direct MP3/AAC, seekable) or ``"hls"`` (m3u8).
        """
        if prefer not in _PREFER_VALUES:
            raise ValueError(f"prefer must be 'progressive' or 'hls'; got {prefer!r}")
        try:
            resource = self._call("https://api-v2.soundcloud.com/resolve", url=track_url)
            transcodings = resource.get("media", {}).get("transcodings") or []
            ordered = sorted(
                transcodings,
                key=lambda t: 0 if t.get("format", {}).get("protocol") == prefer else 1,
            )
            for tc in ordered:
                stream_url = tc.get("url")
                if not stream_url:
                    continue
                data = self._call(stream_url)
                result = data.get("url")
                if result:
                    return result
        except Exception as exc:
            log.debug("resolve_stream failed for %s: %s", track_url, exc)
        return None

    def resolve_user(self, profile_url: str) -> Entity | None:
        """Resolve a profile URL to an Entity via API v2."""
        try:
            u = self._call("https://api-v2.soundcloud.com/resolve", url=profile_url)
            if u.get("kind") != "user":
                return None
            return _user_dict_to_entity({
                "artist": u.get("username") or "",
                "artist_url": u.get("permalink_url") or profile_url,
                "image": u.get("avatar_url") or "",
                "user_id": u.get("id"),
                "country": u.get("country_code") or "",
                "permalink": u.get("permalink") or "",
            })
        except Exception as exc:
            log.debug("resolve_user failed for %s: %s", profile_url, exc)
            return None

    def resolve_track(self, track_url: str) -> Release | None:
        """Resolve a track URL to a Release via API v2."""
        try:
            t = self._call("https://api-v2.soundcloud.com/resolve", url=track_url)
            if t.get("kind") != "track":
                return None
            return _track_dict_to_release(self._parse_track(t))
        except Exception as exc:
            log.debug("resolve_track failed for %s: %s", track_url, exc)
            return None

    # -- download (pure requests, no yt-dlp) ---------------------------------

    @staticmethod
    def _safe_filename(s: str) -> str:
        """Strip characters that are illegal in filenames on common OSes."""
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip()

    def download_track(self, track_url: str, output_dir: str = ".",
                       verbose: bool = False) -> Path:
        """Download a single track via the API — no yt-dlp required.

        Resolves the progressive (direct MP3/AAC) stream URL and streams the
        response to disk.  The filename is derived from the track's real title
        and artist name fetched from the API.

        Parameters
        ----------
        track_url:
            SoundCloud track permalink.
        output_dir:
            Destination directory (created if absent).
        verbose:
            Log progress to debug.

        Returns the path of the saved file.
        Raises ``RuntimeError`` if the stream URL cannot be resolved.
        """
        stream_url = self.resolve_stream(track_url, prefer="progressive")
        if not stream_url:
            raise RuntimeError(f"Could not resolve stream for {track_url}")

        # Fetch metadata for a proper filename
        try:
            resource = self._call("https://api-v2.soundcloud.com/resolve",
                                  url=track_url)
            title = resource.get("title") or track_url.rstrip("/").split("/")[-1]
            artist = (resource.get("user") or {}).get("username") or ""
            if artist and not title.lower().startswith(artist.lower()):
                fname = f"{artist} - {title}.mp3"
            else:
                fname = f"{title}.mp3"
        except Exception:
            fname = track_url.rstrip("/").split("/")[-1] + ".mp3"

        fname = self._safe_filename(fname)
        out = Path(output_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        dest = out / fname

        log.debug("Downloading %s → %s", track_url, dest)
        # stream_url is a pre-signed CDN edge URL (CloudFront/Akamai), not a
        # soundcloud.com endpoint — it isn't Cloudflare-gated, so it doesn't
        # need CloudflareSession/curl_cffi impersonation. Both of those
        # backends buffer the full body regardless of stream=True (curl_cffi
        # has no true streaming mode here, and CloudflareSession._via_curl's
        # kwarg allowlist drops "stream" before it reaches curl_cffi), which
        # would defeat chunked writing for large tracks. Use a plain
        # requests session for this one call so stream=True is honoured.
        with requests.get(stream_url, stream=True, timeout=60,
                          headers=_SC_HEADERS) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

        return dest

    def download_tracks(self, track_urls, output_dir: str = ".",
                        verbose: bool = False) -> list[Path]:
        """Download multiple tracks via the API.

        Returns a list of successfully downloaded file paths; failures are
        logged and omitted.
        """
        results = []
        for url in track_urls:
            try:
                results.append(self.download_track(url, output_dir=output_dir,
                                                   verbose=verbose))
            except Exception as exc:
                log.debug("download_track failed for %s: %s", url, exc)
        return results

    def download_playlist(self, playlist_url: str, output_dir: str = ".",
                          verbose: bool = False) -> list[Path]:
        """Download every track in an artist page or set URL via the API.

        Tracks are saved into a sub-folder named after the artist inside
        *output_dir*.
        """
        tracks = list(self.get_tracks(playlist_url))
        if not tracks:
            return []
        first_credits = tracks[0].work.credits
        artist = (first_credits[0].entity.name if first_credits else None) or "SoundCloud"
        dest_dir = Path(output_dir).expanduser() / self._safe_filename(artist)
        return self.download_tracks(
            (t.uri for t in tracks), output_dir=str(dest_dir), verbose=verbose
        )


# ---------------------------------------------------------------------------
# Backend 2: HTML scraper
# ---------------------------------------------------------------------------

class SoundCloudHTML(SoundCloudBase):
    """HTML page scraping backend.

    No API key or yt-dlp needed for metadata.  Artist/set pages return full
    track metadata (artist, artist_url, duration) via schema.org markup.
    Search result pages return title + URL only (no artwork or duration in
    SoundCloud's search HTML).

    ``resolve_stream()`` delegates to yt-dlp when installed; returns ``None``
    otherwise.  ``resolve_user()`` scrapes Open Graph / JSON-LD from the profile
    page — no API required.

    All track dicts always include the canonical key set; missing values are
    empty string or ``None`` for duration.

    Pass ``session=`` to inject a custom HTTP session (e.g. ``curl_cffi``
    for browser impersonation).  Defaults to :func:`transport.default_session`.
    """

    def __init__(self, session=None):
        self.session = session if session is not None else default_session()

    def _get_soup(self, url: str) -> BeautifulSoup:
        resp = self.session.get(url, timeout=10, headers=_SC_HEADERS)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "html.parser")

    @staticmethod
    def _abs(href: str) -> str:
        return href if href.startswith("http") else "https://soundcloud.com" + href

    @staticmethod
    def _parse_duration(iso: str | None) -> int | None:
        """Parse ISO 8601 duration ``PT00H03M09S`` → seconds, or None on failure."""
        if not iso:
            return None
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        # Require at least one component to be present; reject bare "PT"
        if not m or not any(m.groups()):
            return None
        h, mins, s = (int(x or 0) for x in m.groups())
        return h * 3600 + mins * 60 + s

    def search_tracks(self, query: str, limit: int = 10) -> Iterator[Release]:
        soup = self._get_soup(
            "https://soundcloud.com/search/sounds?q=" + urllib.parse.quote(query)
        )
        for i, h2 in enumerate(soup.find_all("h2")):
            if i >= limit:
                break
            a = h2.find("a")
            if not a:
                continue
            yield _track_dict_to_release({
                "title": a.get_text(strip=True),
                "url": self._abs(a.get("href", "")),
                "artist": "",
                "artist_url": "",
                "image": "",
                "duration": None,
                "track_id": None,
                "user_id": None,
            })

    def search_people(self, query: str, limit: int = 10) -> Iterator[Entity]:
        soup = self._get_soup(
            "https://soundcloud.com/search/people?q=" + urllib.parse.quote(query)
        )
        for i, h2 in enumerate(soup.find_all("h2")):
            if i >= limit:
                break
            a = h2.find("a")
            if not a:
                continue
            href = self._abs(a.get("href", ""))
            yield _user_dict_to_entity({
                "artist": a.get_text(strip=True),
                "artist_url": href,
                "image": "",
                "user_id": None,
            })

    def search_sets(self, query: str, limit: int = 10) -> Iterator[Release]:
        soup = self._get_soup(
            "https://soundcloud.com/search/sets?q=" + urllib.parse.quote(query)
        )
        for i, h2 in enumerate(soup.find_all("h2")):
            if i >= limit:
                break
            a = h2.find("a")
            if not a:
                continue
            href = self._abs(a.get("href", ""))
            yield _set_dict_to_release({
                "title": a.get_text(strip=True),
                "url": href,
                "artist": "",
                "artist_url": "",
                "image": "",
                "playlist_id": None,
                "user_id": None,
            })

    def get_tracks(self, url: str, limit: int = 20) -> Iterator[Release]:
        """Scrape tracks from an artist or set page.

        Extracts title, URL, artist, artist_url, and duration from the
        schema.org MusicRecording markup — no extra requests, no yt-dlp.
        Images are not available via HTML scraping (empty string).
        """
        soup = self._get_soup(url)
        collected = 0
        for item in soup.find_all("article", itemprop="track"):
            if collected >= limit:
                break
            try:
                h2 = item.find("h2", itemprop="name")
                if not h2:
                    continue
                links = h2.find_all("a")
                if not links:
                    continue
                track_a = links[0]
                track_href = self._abs(track_a.get("href", ""))
                if track_href == url:
                    continue
                title = track_a.get_text(strip=True)
                artist_name, artist_href = "", ""
                if len(links) >= 2:
                    artist_a = links[1]
                    artist_name = artist_a.get_text(strip=True)
                    artist_href = self._abs(artist_a.get("href", ""))
                dur_meta = item.find("meta", itemprop="duration")
                duration = self._parse_duration(
                    dur_meta.get("content") if dur_meta else None
                )
                yield _track_dict_to_release({
                    "title": title,
                    "url": track_href,
                    "artist": artist_name,
                    "artist_url": artist_href,
                    "image": "",
                    "duration": duration,
                    "track_id": None,
                    "user_id": None,
                })
                collected += 1
            except Exception as exc:
                log.debug("HTML get_tracks parse error: %s", exc)
                continue

    def resolve_stream(self, track_url: str, prefer: str = "progressive") -> str | None:
        """Not supported by the HTML backend.

        SoundCloud stream URLs are signed and not available in page HTML.
        Use ``SoundCloudAPI`` or ``SoundCloudYTDLP`` for stream resolution.
        """
        raise NotImplementedError(
            "SoundCloudHTML cannot resolve stream URLs. "
            "Use SoundCloudAPI (no extra deps) or SoundCloudYTDLP."
        )

    def resolve_user(self, profile_url: str) -> Entity | None:
        """Scrape display name and avatar from a profile page via Open Graph / JSON-LD."""
        import json as _json  # noqa: PLC0415
        try:
            soup = self._get_soup(profile_url)
            artist: str | None = None
            image: str | None = None

            og_title = soup.find("meta", property="og:title")
            if og_title:
                artist = og_title.get("content", "").split(" |")[0].strip() or None
            og_img = soup.find("meta", property="og:image")
            if og_img:
                image = og_img.get("content")

            if not artist:
                ld = soup.find("script", type="application/ld+json")
                if ld:
                    try:
                        artist = _json.loads(ld.string or "{}").get("name") or None
                    except Exception:
                        pass

            if not artist:
                return None
            return _user_dict_to_entity({"artist": artist, "artist_url": profile_url,
                                         "image": image or "", "user_id": None})
        except Exception as exc:
            log.debug("HTML resolve_user failed for %s: %s", profile_url, exc)
            return None

    def resolve_track(self, track_url: str) -> Release | None:
        """Best-effort scrape of a track page — no numeric ids.

        SoundCloud doesn't expose the track id in plain HTML in a stable
        location, so this backend returns ``track_id``/``user_id`` as
        ``None``. Callers needing the numeric id should let the
        :class:`SoundCloud` orchestrator fall through to the API v2 or
        yt-dlp backends.
        """
        try:
            meta = self.get_track_meta(track_url)
        except Exception as exc:
            log.debug("HTML resolve_track failed for %s: %s", track_url, exc)
            return None
        if not meta:
            return None
        soup = self._get_soup(track_url)
        og_title = soup.find("meta", property="og:title")
        title = og_title.get("content", "").strip() if og_title else ""
        return _track_dict_to_release({
            "title": title,
            "url": track_url,
            "artist": meta.get("artist") or "",
            "artist_url": "",
            "image": meta.get("image") or "",
            "duration": None,
            "track_id": None,
            "user_id": None,
        })

    # -- HTML-specific helpers -----------------------------------------------

    def get_track_meta(self, track_url: str) -> dict:
        """Scrape artist name and thumbnail from a track page (no yt-dlp).

        Makes one extra HTTP request.  Use ``get_tracks()`` on an artist page
        for bulk metadata without extra requests.
        """
        import json as _json  # noqa: PLC0415
        soup = self._get_soup(track_url)
        image, artist = None, None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content")
        ld = soup.find("script", type="application/ld+json")
        if ld:
            try:
                artist = (_json.loads(ld.string or "{}").get("author") or {}).get("name")
            except Exception:
                pass
        if not artist:
            tag = soup.find("a", attrs={"itemprop": "url"})
            if tag:
                artist = tag.get_text(strip=True)
        return {k: v for k, v in {"artist": artist, "image": image}.items() if v}

    def search_tracks_enriched(self, query: str, limit: int = 10) -> Iterator[Release]:
        """search_tracks with artist + image added (one extra HTTP request per track).

        Prefer ``SoundCloudAPI.search_tracks()`` when full metadata is needed
        without extra requests.
        """
        for release in self.search_tracks(query, limit=limit):
            try:
                meta = self.get_track_meta(release.uri)
                artist = meta.get("artist") or ""
                image = meta.get("image") or ""
                updates: dict = {}
                if artist and not release.work.credits:
                    artist_ref = EntityRef(name=artist, kind=EntityKind.PERSON)
                    new_credits = [Credit(entity=artist_ref, role="artist",
                                         relation_role=RelationRole.PERFORMER,
                                         section=CreditSection.PRINCIPAL)]
                    updates["work"] = release.work.model_copy(
                        update={"credits": new_credits}
                    )
                if image and not release.image:
                    updates["image"] = image
                if updates:
                    release = release.model_copy(update=updates)
            except Exception as exc:
                log.debug("Enrichment failed for %s: %s", release.uri, exc)
            yield release


# Keep old name as alias for backwards compatibility
SoundCloudScraper = SoundCloudHTML


# ---------------------------------------------------------------------------
# Backend 3: yt-dlp
# ---------------------------------------------------------------------------

class SoundCloudYTDLP(SoundCloudBase):
    """yt-dlp backed SoundCloud client.

    All operations go through yt-dlp.  Provides the most resilient stream
    resolution (yt-dlp tends to be patched faster when SoundCloud rotates
    their signing scheme), but is slower and has no people/set search.

    ``search_people()`` and ``search_sets()`` yield nothing — yt-dlp does not
    expose those endpoints.

    Requires ``pip install nuvem_de_som[yt-dlp]``.
    """

    @staticmethod
    def _ydl(extra_opts: dict | None = None):
        yt_dlp = _ydl_import()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        opts.update(extra_opts or {})
        return yt_dlp.YoutubeDL(opts)

    @staticmethod
    def _entry_to_track(entry: dict, artist_url: str = "") -> dict:
        raw_id = entry.get("id")
        try:
            track_id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            track_id = None
        return {
            "title": entry.get("title") or "",
            "url": entry.get("url") or entry.get("webpage_url") or "",
            "artist": entry.get("uploader") or entry.get("channel") or "",
            "artist_url": artist_url,
            "image": entry.get("thumbnail") or "",
            "duration": entry.get("duration"),
            "track_id": track_id,
            "user_id": None,
        }

    def search_tracks(self, query: str, limit: int = 10) -> Iterator[Release]:
        with self._ydl() as ydl:
            info = ydl.extract_info(f"scsearch{limit}:{query}", download=False) or {}
        for entry in info.get("entries") or []:
            yield _track_dict_to_release(self._entry_to_track(entry))

    def search_people(self, query: str, limit: int = 10) -> Iterator[Entity]:
        # yt-dlp has no people search endpoint
        return iter([])

    def search_sets(self, query: str, limit: int = 10) -> Iterator[Release]:
        # yt-dlp has no set search endpoint
        return iter([])

    def get_tracks(self, url: str, limit: int = 200) -> Iterator[Release]:
        with self._ydl({"playlistend": limit}) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        artist_url = url if "/sets/" not in url else ""
        for entry in info.get("entries") or []:
            yield _track_dict_to_release(self._entry_to_track(entry, artist_url=artist_url))

    def resolve_stream(self, track_url: str, prefer: str = "progressive") -> str | None:
        """Resolve stream URL via yt-dlp full extraction."""
        if prefer not in _PREFER_VALUES:
            raise ValueError(f"prefer must be 'progressive' or 'hls'; got {prefer!r}")
        try:
            yt_dlp = _ydl_import()
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(track_url, download=False) or {}
                formats = info.get("formats") or []
                target_protocol = "https" if prefer == "progressive" else "m3u8_native"
                for f in reversed(formats):
                    if f.get("protocol") == target_protocol:
                        return f["url"]
                # fall back to any format if preferred protocol not found
                return formats[-1]["url"] if formats else info.get("url")
        except ImportError:
            raise
        except Exception as exc:
            log.debug("yt-dlp resolve_stream failed for %s: %s", track_url, exc)
            return None

    def resolve_user(self, profile_url: str) -> Entity | None:
        """Resolve user metadata via yt-dlp channel extraction."""
        try:
            yt_dlp = _ydl_import()
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                   "extract_flat": True, "playlistend": 0}) as ydl:
                info = ydl.extract_info(profile_url, download=False) or {}
            uploader = info.get("uploader") or info.get("channel") or ""
            if not uploader:
                return None
            return _user_dict_to_entity({
                "artist": uploader,
                "artist_url": profile_url,
                "image": info.get("thumbnail") or "",
                "user_id": info.get("uploader_id") or None,
            })
        except ImportError:
            raise
        except Exception as exc:
            log.debug("yt-dlp resolve_user failed for %s: %s", profile_url, exc)
            return None

    def resolve_track(self, track_url: str) -> Release | None:
        """Resolve a track URL via yt-dlp metadata extraction.

        Backends without a v2 ``/resolve`` endpoint fall back to yt-dlp's
        full metadata pull. The ``track_id`` is what SoundCloud's HTML
        encodes via ``soundcloud:tracks:<id>``.
        """
        try:
            yt_dlp = _ydl_import()
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(track_url, download=False) or {}
        except ImportError:
            raise
        except Exception as exc:
            log.debug("yt-dlp resolve_track failed for %s: %s", track_url, exc)
            return None
        # Pass-through other extractors too — caller asked us to resolve.
        track_id = info.get("id")
        try:
            track_id = int(track_id) if track_id is not None else None
        except (TypeError, ValueError):
            pass
        return _track_dict_to_release({
            "title": info.get("title") or "",
            "url": info.get("webpage_url") or track_url,
            "artist": info.get("uploader") or info.get("artist") or "",
            "artist_url": info.get("uploader_url") or "",
            "image": info.get("thumbnail") or "",
            "duration": info.get("duration"),
            "track_id": track_id,
            "user_id": info.get("uploader_id") or None,
        })

    # -- download ------------------------------------------------------------

    def _download_urls(self, urls: list[str], output_dir: str,
                       verbose: bool, outtmpl_suffix: str) -> list[Path]:
        yt_dlp = _ydl_import()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        outtmpl = str(out / outtmpl_suffix)
        downloaded: list[Path] = []

        class _Hook:
            def __call__(self, d):
                if d["status"] == "finished":
                    downloaded.append(Path(d["filename"]))

        opts = {
            "quiet": not verbose,
            "outtmpl": outtmpl,
            "progress_hooks": [_Hook()],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(urls)
        return downloaded

    def download_track(self, track_url: str, output_dir: str = ".",
                       verbose: bool = False) -> Path | None:
        """Download a single track via yt-dlp in its native format.

        Returns the path of the downloaded file, or ``None`` on failure.
        """
        files = self._download_urls(
            [track_url], output_dir, verbose,
            outtmpl_suffix="%(uploader)s - %(title)s.%(ext)s",
        )
        return files[0] if files else None

    def download_tracks(self, track_urls, output_dir: str = ".",
                        verbose: bool = False) -> list[Path]:
        """Download multiple tracks via yt-dlp.

        Returns only paths of successfully downloaded files.
        """
        results = []
        for u in track_urls:
            path = self.download_track(u, output_dir=output_dir, verbose=verbose)
            if path is not None:
                results.append(path)
        return results

    def download_playlist(self, playlist_url: str, output_dir: str = ".",
                          verbose: bool = False) -> list[Path]:
        """Download every track in an artist page or set URL via yt-dlp.

        A sub-folder named after the artist is created automatically inside
        *output_dir*.
        """
        return self._download_urls(
            [playlist_url], output_dir, verbose,
            outtmpl_suffix="%(uploader)s/%(title)s.%(ext)s",
        )


# ---------------------------------------------------------------------------
# Orchestrator — subclass of SoundCloudBase, falls through to concrete backends
# ---------------------------------------------------------------------------

class SoundCloud(SoundCloudBase):
    """SoundCloud orchestrator — API v2 → yt-dlp → HTML, with transparent fallback.

    Use the concrete classes directly when you need a specific backend:

    - ``SoundCloudAPI()``    — full metadata, no yt-dlp
    - ``SoundCloudHTML()``   — HTML scraper, no extra deps
    - ``SoundCloudYTDLP()``  — yt-dlp backed stream resolution

    Pass ``session=`` to inject a custom HTTP session for the API and HTML
    backends.  Note: :class:`SoundCloudYTDLP` uses yt-dlp internally and
    does NOT honour an injected session.
    """

    def __init__(self, session=None):
        self.session = session if session is not None else default_session()
        self._chain: list[SoundCloudBase] = [
            SoundCloudAPI(session=self.session),
            SoundCloudYTDLP(),
            SoundCloudHTML(session=self.session),
        ]

    def _try_each(self, method: str, *args, **kwargs) -> Iterator[dict]:
        """Yield from the first backend that returns results without raising."""
        for b in self._chain:
            try:
                results = list(getattr(b, method)(*args, **kwargs))
                if results:
                    yield from results
                    return
            except Exception as exc:
                log.debug("%s.%s failed, trying next backend: %s",
                          type(b).__name__, method, exc)
                continue

    def _try_each_value(self, method: str, *args, **kwargs):
        """Return the first non-None result across backends."""
        for b in self._chain:
            try:
                result = getattr(b, method)(*args, **kwargs)
                if result is not None:
                    return result
            except Exception as exc:
                log.debug("%s.%s failed, trying next backend: %s",
                          type(b).__name__, method, exc)
                continue
        return None

    def search_tracks(self, query: str, limit: int = 10) -> Iterator[Release]:
        yield from self._try_each("search_tracks", query, limit=limit)

    def search_people(self, query: str, limit: int = 10) -> Iterator[Entity]:
        yield from self._try_each("search_people", query, limit=limit)

    def search_sets(self, query: str, limit: int = 10) -> Iterator[Release]:
        yield from self._try_each("search_sets", query, limit=limit)

    def get_tracks(self, url: str, limit: int = 200) -> Iterator[Release]:
        yield from self._try_each("get_tracks", url, limit=limit)

    def resolve_stream(self, track_url: str, prefer: str = "progressive") -> str | None:
        if prefer not in _PREFER_VALUES:
            raise ValueError(f"prefer must be 'progressive' or 'hls'; got {prefer!r}")
        return self._try_each_value("resolve_stream", track_url, prefer=prefer)

    def resolve_user(self, profile_url: str) -> Entity | None:
        return self._try_each_value("resolve_user", profile_url)

    def resolve_track(self, track_url: str) -> Release | None:
        return self._try_each_value("resolve_track", track_url)

    # -- downloads (API first, yt-dlp fallback) ------------------------------

    @property
    def _api(self) -> SoundCloudAPI:
        for b in self._chain:
            if isinstance(b, SoundCloudAPI):
                return b
        raise RuntimeError("SoundCloudAPI backend not found in chain")

    @property
    def _ytdlp(self) -> SoundCloudYTDLP:
        for b in self._chain:
            if isinstance(b, SoundCloudYTDLP):
                return b
        raise RuntimeError("SoundCloudYTDLP backend not found in chain")

    def download_track(self, track_url: str, output_dir: str = ".",
                       verbose: bool = False) -> Path | None:
        """Download a single track.

        Tries the API backend first (pure requests, no extra deps).  Falls back
        to ``SoundCloudYTDLP`` if the API stream fails — yt-dlp must be
        installed for the fallback (``pip install nuvem_de_som[yt-dlp]``).
        """
        try:
            return self._api.download_track(track_url, output_dir=output_dir,
                                            verbose=verbose)
        except Exception as exc:
            log.debug("API download failed for %s (%s), trying yt-dlp", track_url, exc)
        return self._ytdlp.download_track(track_url, output_dir=output_dir,
                                          verbose=verbose)

    def download_tracks(self, track_urls, output_dir: str = ".",
                        verbose: bool = False) -> list[Path]:
        """Download multiple tracks (API first, yt-dlp fallback per track)."""
        results = []
        for url in track_urls:
            path = self.download_track(url, output_dir=output_dir, verbose=verbose)
            if path is not None:
                results.append(path)
        return results

    def download_playlist(self, playlist_url: str, output_dir: str = ".",
                          verbose: bool = False) -> list[Path]:
        """Download every track in an artist page or set URL.

        Tries the API backend first (no yt-dlp required).  Falls back to
        yt-dlp if the API stream fails.
        """
        try:
            return self._api.download_playlist(playlist_url, output_dir=output_dir,
                                               verbose=verbose)
        except Exception as exc:
            log.debug("API download_playlist failed (%s), trying yt-dlp", exc)
        return self._ytdlp.download_playlist(playlist_url, output_dir=output_dir,
                                             verbose=verbose)
