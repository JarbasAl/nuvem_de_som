# Backends reference

## Capability matrix

| Backend | `search_tracks` | `search_people` | `search_sets` | `get_tracks` | `resolve_stream` | `resolve_track` | `resolve_user` | `crawl` | `download_*` |
|---|---|---|---|---|---|---|---|---|---|
| `SoundCloudAPI` | full metadata | full metadata | full metadata | user + playlist | progressive / HLS | yes | yes | social-graph BFS | pure requests |
| `SoundCloudHTML` | title+URL only | name+URL only | title+URL only | full from schema.org | `NotImplementedError` | best-effort | Open Graph / JSON-LD | flat expansion | n/a |
| `SoundCloudYTDLP` | full metadata | nothing | nothing | yes | progressive / HLS | yes | yes | flat expansion | yt-dlp |
| `SoundCloud` | API, then yt-dlp, then HTML | API, then HTML | API | API, then yt-dlp, then HTML | API, then yt-dlp | API, then yt-dlp, then HTML | API, then yt-dlp, then HTML | API BFS | API first, yt-dlp fallback |

---

## SoundCloudAPI

`nuvem_de_som.__init__.SoundCloudAPI`: `nuvem_de_som/__init__.py:457`

Uses the SoundCloud internal API v2. It fetches a `client_id` from
SoundCloud's bundled JS on first use, caches it globally, and refreshes it
automatically on a 401 or 403 response.

- `search_tracks(query, limit=10)`: `GET /search/tracks`: full metadata per track
- `search_people(query, limit=10)`: `GET /search/users`
- `search_sets(query, limit=10)`: `GET /search/playlists`: includes `Work.tracklist`
- `get_tracks(url, limit=200)`: resolves the URL, then paginates `/users/{id}/tracks` or reads playlist tracks inline
- `resolve_stream(track_url, prefer="progressive")`: resolves the transcodings endpoint, returns a direct URL
- `resolve_track(track_url)`: `GET /resolve` → `Release`
- `resolve_user(profile_url)`: `GET /resolve` → `Entity`
- `get_followers(profile_url, limit=200)`: paginates `/users/{id}/followers` → `Iterator[Entity]`
- `get_following(profile_url, limit=200)`: paginates `/users/{id}/followings` → `Iterator[Entity]`
- `get_reposts(profile_url, limit=50)`: paginates `/stream/users/{id}/reposts` → `Iterator[Release]`
- `crawl(seeds, *, social_depth=50, max_artists=0, seen=None)`: BFS artist discovery over followers and followings → `Iterator[Entity]`, seeds can be profile URLs or keyword queries
- `download_track(track_url, output_dir=".", verbose=False)`: progressive stream over requests, returns a `Path`
- `download_tracks(track_urls, output_dir=".", verbose=False)`: returns `list[Path]`
- `download_playlist(playlist_url, output_dir=".", verbose=False)`: saves into `output_dir/<artist>/`

Inject a custom session:

```python
sc = SoundCloudAPI(session=my_session)
```

### `crawl()`: social-graph BFS

`SoundCloudAPI.crawl()` overrides the base implementation with a real BFS
that expands each artist's followers and followings. The base
`SoundCloudBase.crawl()` is the flat fallback used by `SoundCloudHTML` and
`SoundCloudYTDLP`. It resolves URL seeds directly and expands keyword seeds
with `search_people`, without fetching any follower graph.

```python
sc = SoundCloudAPI()
seen = set()
for entity in sc.crawl(["https://soundcloud.com/noisia", "black metal"],
                        social_depth=20, max_artists=50, seen=seen):
    print(entity.name, entity.extra.get("followers_count", "?"))
```

The `crawl()` call mutates the `seen` set in place. Reuse it across calls to
resume a crawl without visiting the same profile twice.

---

## SoundCloudHTML

`nuvem_de_som.__init__.SoundCloudHTML`: `nuvem_de_som/__init__.py:758`

Scrapes SoundCloud's public HTML. It needs no API key.

- `search_tracks` / `search_people` / `search_sets`: parses `<h2>` tags from search pages, and returns title and URL only (no artwork, duration, or artist on search-result pages)
- `get_tracks(url, limit=20)`: extracts `<article itemprop="track">` schema.org markup, and provides title, URL, artist, `artist_url`, and duration
- `search_tracks_enriched(query, limit=10)`: like `search_tracks` but adds artist and image with one extra `GET` per track
- `get_track_meta(track_url)`: scrapes artist name and artwork from a single track page (one extra request)
- `resolve_user(profile_url)`: scrapes Open Graph `og:title` / `og:image` and JSON-LD, and returns an `Entity` or `None`
- `resolve_track(track_url)`: best-effort scrape, with no numeric IDs, so use the orchestrator for full metadata
- `resolve_stream(...)`: always raises `NotImplementedError`

`SoundCloudScraper` is an alias kept for backward compatibility.

Inject a custom session:

```python
sc = SoundCloudHTML(session=my_session)
```

---

## SoundCloudYTDLP

`nuvem_de_som.__init__.SoundCloudYTDLP`: `nuvem_de_som/__init__.py:1044`

Needs `pip install nuvem_de_som[yt-dlp]`.

- `search_tracks(query, limit=10)`: uses the `scsearch{limit}:{query}` yt-dlp URL
- `search_people` / `search_sets`: yield nothing (yt-dlp has no endpoint for these)
- `get_tracks(url, limit=200)`: uses `extract_flat=True`, respects `playlistend`
- `resolve_stream(track_url, prefer="progressive")`: full yt-dlp extraction, mapping `prefer="progressive"` to `protocol="https"`, and `prefer="hls"` to `protocol="m3u8_native"`
- `resolve_track(track_url)`: full yt-dlp metadata pull
- `resolve_user(profile_url)`: channel extraction, `playlistend=0`
- `download_track(track_url, output_dir=".", verbose=False)`: yt-dlp native format, returns `Path | None`
- `download_tracks(track_urls, ...)`: sequential, returns `list[Path]`
- `download_playlist(playlist_url, ...)`: saves into `output_dir/%(uploader)s/%(title)s.%(ext)s`

Does not accept a `session=` keyword argument. yt-dlp manages its own HTTP.

---

## SoundCloud (orchestrator)

`nuvem_de_som.__init__.SoundCloud`: `nuvem_de_som/__init__.py:1250`

A subclass of `SoundCloudBase`. It holds a chain of
`[SoundCloudAPI, SoundCloudYTDLP, SoundCloudHTML]`.

- Generator methods (`search_*`, `get_tracks`) call `_try_each`. It walks the chain and returns results from the first backend that yields at least one item without raising.
- Single-value methods (`resolve_*`) call `_try_each_value`. It returns the first non-`None` result.
- Download methods try `SoundCloudAPI` first. On any exception, they fall back to `SoundCloudYTDLP`.

```python
sc = SoundCloud()                         # default_session() for API + HTML
sc = SoundCloud(session=my_session)       # custom session forwarded to API + HTML
```

---
[← Getting started](getting-started.md) · [Home](../README.md) · [Streams and transcodings →](streams.md)
