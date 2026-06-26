# Backends reference

## Capability matrix

| Backend | `search_tracks` | `search_people` | `search_sets` | `get_tracks` | `resolve_stream` | `resolve_track` | `resolve_user` | `crawl` | `download_*` |
|---|---|---|---|---|---|---|---|---|---|
| `SoundCloudAPI` | full metadata | full metadata | full metadata | user + playlist | progressive / HLS | yes | yes | social-graph BFS | pure requests |
| `SoundCloudHTML` | title+URL only | name+URL only | title+URL only | full from schema.org | `NotImplementedError` | best-effort | Open Graph / JSON-LD | flat expansion | — |
| `SoundCloudYTDLP` | full metadata | nothing | nothing | yes | progressive / HLS | yes | yes | flat expansion | yt-dlp |
| `SoundCloud` | API → yt-dlp → HTML | API → HTML | API | API → yt-dlp → HTML | API → yt-dlp | API → yt-dlp → HTML | API → yt-dlp → HTML | API BFS | API first, yt-dlp fallback |

---

## SoundCloudAPI

`nuvem_de_som.__init__.SoundCloudAPI` — `nuvem_de_som/__init__.py:457`

Uses SoundCloud internal API v2. Fetches a `client_id` from their bundled JS on first use,
caches it globally, refreshes automatically on 401/403.

- `search_tracks(query, limit=10)` — `GET /search/tracks` — full metadata per track
- `search_people(query, limit=10)` — `GET /search/users`
- `search_sets(query, limit=10)` — `GET /search/playlists` — includes `Work.tracklist`
- `get_tracks(url, limit=200)` — resolves URL, paginates `/users/{id}/tracks` or reads playlist tracks inline
- `resolve_stream(track_url, prefer="progressive")` — resolves transcodings endpoint, returns direct URL
- `resolve_track(track_url)` — `GET /resolve` → `Release`
- `resolve_user(profile_url)` — `GET /resolve` → `Entity`
- `get_followers(profile_url, limit=200)` — paginates `/users/{id}/followers` → `Iterator[Entity]`
- `get_following(profile_url, limit=200)` — paginates `/users/{id}/followings` → `Iterator[Entity]`
- `get_reposts(profile_url, limit=50)` — paginates `/stream/users/{id}/reposts` → `Iterator[Release]`
- `crawl(seeds, *, social_depth=50, max_artists=0, seen=None)` — BFS artist discovery via followers + followings → `Iterator[Entity]`; seeds may be profile URLs or keyword queries
- `download_track(track_url, output_dir=".", verbose=False)` — progressive stream via requests, returns `Path`
- `download_tracks(track_urls, output_dir=".", verbose=False)` — returns `list[Path]`
- `download_playlist(playlist_url, output_dir=".", verbose=False)` — saves into `output_dir/<artist>/`

Inject a custom session:

```python
sc = SoundCloudAPI(session=my_session)
```

### `crawl()` — social-graph BFS

`SoundCloudAPI.crawl()` overrides the base implementation with a proper BFS
that expands each artist's followers and followings.  The base
`SoundCloudBase.crawl()` is the flat fallback used by `SoundCloudHTML` and
`SoundCloudYTDLP`: it resolves URL seeds directly and expands keyword seeds
via `search_people`, without fetching any follower graph.

```python
sc = SoundCloudAPI()
seen = set()
for entity in sc.crawl(["https://soundcloud.com/noisia", "black metal"],
                        social_depth=20, max_artists=50, seen=seen):
    print(entity.name, entity.extra.get("followers_count", "?"))
```

The `seen` set is mutated in-place.  Re-use it across calls to resume a
crawl without revisiting profiles.

---

## SoundCloudHTML

`nuvem_de_som.__init__.SoundCloudHTML` — `nuvem_de_som/__init__.py:758`

Scrapes SoundCloud's public HTML. No API key needed.

- `search_tracks` / `search_people` / `search_sets` — parses `<h2>` tags from search pages; returns title + URL only (no artwork, duration, or artist on search results pages)
- `get_tracks(url, limit=20)` — extracts `<article itemprop="track">` schema.org markup; provides title, URL, artist, `artist_url`, and duration
- `search_tracks_enriched(query, limit=10)` — like `search_tracks` but adds artist + image via one extra `GET` per track
- `get_track_meta(track_url)` — scrapes artist name and artwork from a single track page (one extra request)
- `resolve_user(profile_url)` — scrapes Open Graph `og:title` / `og:image` and JSON-LD; returns `Entity` or `None`
- `resolve_track(track_url)` — best-effort scrape; no numeric IDs; use orchestrator for full metadata
- `resolve_stream(...)` — always raises `NotImplementedError`

`SoundCloudScraper` is an alias for backwards compatibility.

Inject a custom session:

```python
sc = SoundCloudHTML(session=my_session)
```

---

## SoundCloudYTDLP

`nuvem_de_som.__init__.SoundCloudYTDLP` — `nuvem_de_som/__init__.py:1044`

Requires `pip install nuvem_de_som[yt-dlp]`.

- `search_tracks(query, limit=10)` — uses `scsearch{limit}:{query}` yt-dlp URL
- `search_people` / `search_sets` — yield nothing (yt-dlp has no endpoint for these)
- `get_tracks(url, limit=200)` — `extract_flat=True`, respects `playlistend`
- `resolve_stream(track_url, prefer="progressive")` — full yt-dlp extraction; maps `prefer="progressive"` to `protocol="https"`, `prefer="hls"` to `protocol="m3u8_native"`
- `resolve_track(track_url)` — full yt-dlp metadata pull
- `resolve_user(profile_url)` — channel extraction, `playlistend=0`
- `download_track(track_url, output_dir=".", verbose=False)` — yt-dlp native format, returns `Path | None`
- `download_tracks(track_urls, ...)` — sequential, returns `list[Path]`
- `download_playlist(playlist_url, ...)` — saves into `output_dir/%(uploader)s/%(title)s.%(ext)s`

Does **not** accept a `session=` kwarg — yt-dlp manages its own HTTP.

---

## SoundCloud (orchestrator)

`nuvem_de_som.__init__.SoundCloud` — `nuvem_de_som/__init__.py:1250`

Subclass of `SoundCloudBase`. Holds a chain `[SoundCloudAPI, SoundCloudYTDLP, SoundCloudHTML]`.

- Generator methods (`search_*`, `get_tracks`) call `_try_each`: iterates the chain, returns results from the first backend that yields at least one item without raising.
- Single-value methods (`resolve_*`) call `_try_each_value`: returns the first non-`None` result.
- Download methods try `SoundCloudAPI` first; on any exception fall back to `SoundCloudYTDLP`.

```python
sc = SoundCloud()                         # default_session() for API + HTML
sc = SoundCloud(session=my_session)       # custom session forwarded to API + HTML
```
