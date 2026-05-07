# nuvem_de_som API

`nuvem_de_som` searches, streams, and downloads SoundCloud content.

## Architecture

```
SoundCloudBase  (abstract)
├── SoundCloudAPI    — internal API v2, full metadata, recommended
├── SoundCloudHTML   — HTML scraper, no extra deps
├── SoundCloudYTDLP  — yt-dlp backed, best stream resolution
└── SoundCloud       — orchestrator subclass, tries API → yt-dlp → HTML
```

All backends implement the same interface. Metadata retrieval methods return
[`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) objects:

- **track methods** (`search_tracks`, `get_tracks`, `resolve_track`) yield/return `mediavocab.Release`
- **people/user methods** (`search_people`, `resolve_user`) yield/return `mediavocab.Entity`
- **set methods** (`search_sets`) yield `mediavocab.Release`

### Release fields (tracks and sets)

```python
release.uri                          # SoundCloud permalink
release.image                        # artwork URL ("" when not available)
release.stream_mode                  # StreamMode.ON_DEMAND
release.work.title                   # track / set title
release.work.media_type              # MediaType.MUSIC
release.work.runtime                 # duration in seconds (float or None)
release.work.credits                 # list[Credit]; empty when artist unknown
release.work.credits[0].entity.name  # artist display name
release.work.credits[0].entity.external_ids.get("soundcloud_user_id")
release.work.extra.get("artist_url") # artist profile URL
release.work.external_ids.get("soundcloud_track_id")
release.work.external_ids.get("soundcloud_user_id")
# sets also have:
release.external_ids.get("soundcloud_playlist_id")
release.work.tracklist               # list[Appearance], positions 1..N
```

### Enriched fields populated from the SoundCloud API

The ``SoundCloudAPI`` backend (and the ``SoundCloud`` orchestrator when
it falls through to it) populates the following fields from the live
v2 response when SoundCloud exposes them:

| mediavocab field | source on SoundCloud track JSON |
| --- | --- |
| ``Work.aka`` | ``permalink`` (URL slug) |
| ``Work.content_genres`` | ``genre`` + ``tag_list`` (mapped to ``GENRE_*`` when recognised) |
| ``Work.country`` | uploader ``country_code`` |
| ``Work.tracklist`` | ``tracks[]`` of a playlist/set, as typed ``Appearance`` |
| ``Release.codec`` | best ``media.transcodings[].format.mime_type`` |
| ``Release.bitrate`` | ``"256"`` (hq) / ``"128"`` (sq) from transcoding ``quality`` |
| ``Release.audio_channels`` | ``"stereo"`` (SoundCloud is always 2-channel) |
| ``Release.license`` | ``license`` mapped to SPDX (e.g. ``cc-by-nc`` → ``CC-BY-NC-4.0``); ``all-rights-reserved`` is preserved verbatim |
| ``Release.release_date`` | ``display_date`` / ``created_at`` truncated to ISO date |
| ``Entity.extra["country"]`` | uploader ``country_code`` |
| ``Entity.extra["permalink"]`` | profile URL slug |

The ``SoundCloudHTML`` backend cannot recover these fields from page
HTML; they will be empty/default when an HTML-only path is used.

### Entity fields (artists / users)

```python
entity.name                          # display name
entity.kind                          # EntityKind.PERSON
entity.external_ids.get("soundcloud_user_id")
entity.extra.get("artist_url")       # profile URL
entity.extra.get("image")            # avatar URL
```

> **Note:** `SoundCloudYTDLP.search_people()` and `search_sets()` yield nothing —
> yt-dlp has no people/set search endpoint.
>
> `SoundCloudHTML.search_tracks()` / `search_people()` / `search_sets()` return
> limited metadata from SoundCloud's search HTML (title + URL only); use
> `get_tracks()` on an artist/set page for full metadata including duration.

---

## Quick start

```python
from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP

sc = SoundCloud()        # orchestrator: API → yt-dlp → HTML fallback
sc = SoundCloudAPI()     # API only (full metadata, recommended)
sc = SoundCloudHTML()    # HTML scraper only (no extra deps)
sc = SoundCloudYTDLP()   # yt-dlp only (requires pip install nuvem_de_som[yt-dlp])

for release in sc.search_tracks("nuclear chill", limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.work.runtime)
```

---

## SoundCloudAPI (recommended)

Uses SoundCloud's internal API v2.  Returns full metadata in one call.
Requires only `requests` — no yt-dlp for search, listing, or stream resolution.

```python
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

# Track search → Release objects
for release in sc.search_tracks("nuclear chill", limit=5):
    print(release.work.title, release.work.runtime)

# People search → Entity objects
for entity in sc.search_people("acidkid"):
    print(entity.name, entity.extra.get("artist_url"), entity.extra.get("image"))

# Playlist/set search → Release objects
for release in sc.search_sets("chill", limit=5):
    print(release.work.title, release.work.credits[0].entity.name if release.work.credits else "")

# Enumerate all tracks for an artist or set (paginates the full catalogue)
for release in sc.get_tracks("https://soundcloud.com/acidkid", limit=200):
    print(release.work.title)

for release in sc.get_tracks("https://soundcloud.com/acidkid/sets/beathop"):
    print(release.work.title)

# Resolve a track URL to a direct stream (no yt-dlp required)
stream_url = sc.resolve_stream("https://soundcloud.com/acidkid/nuclear-chill")
stream_url = sc.resolve_stream("...", prefer="hls")    # default: "progressive"

# Resolve a profile URL → Entity
entity = sc.resolve_user("https://soundcloud.com/acidkid")
# entity.name, entity.extra["artist_url"], entity.extra["image"]

# Resolve a track URL → Release
release = sc.resolve_track("https://soundcloud.com/acidkid/nuclear-chill")
```

---

## SoundCloudHTML (no-dep fallback)

Parses SoundCloud's public HTML.  No API key.

- **Artist / set pages** (`get_tracks()`): extracts full metadata including
  artist, artist_url, and duration from schema.org `MusicRecording` markup —
  no extra requests, no yt-dlp.
- **Search pages** (`search_tracks()`, `search_people()`, `search_sets()`):
  SoundCloud's search HTML is sparse — only title + URL are available.
  Use `search_tracks_enriched()` to add metadata at the cost of one extra
  request per track.

```python
from nuvem_de_som import SoundCloudHTML

sc = SoundCloudHTML()

# Artist page — full metadata from schema.org markup
for release in sc.get_tracks("https://soundcloud.com/acidkid", limit=20):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.work.runtime)  # runtime in seconds

# Search — title + URL only (credits/image/runtime are empty/None)
for release in sc.search_tracks("nuclear chill", limit=5):
    print(release.work.title, release.uri)

# Enriched search — adds artist + image via one extra request per track
for release in sc.search_tracks_enriched("nuclear chill", limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist)

# resolve_user scrapes Open Graph / JSON-LD (no API required) → Entity
entity = sc.resolve_user("https://soundcloud.com/acidkid")

# resolve_stream raises NotImplementedError — HTML has no stream access
# Use SoundCloudAPI or SoundCloudYTDLP for stream resolution
```

---

## SoundCloudYTDLP (last resort)

All operations backed by yt-dlp.  Best stream resolution resilience; slower.
No people or set search.  Requires `pip install nuvem_de_som[yt-dlp]`.

```python
from nuvem_de_som import SoundCloudYTDLP

sc = SoundCloudYTDLP()

for release in sc.search_tracks("nuclear chill", limit=5):
    print(release.work.title)

for release in sc.get_tracks("https://soundcloud.com/acidkid"):
    print(release.work.title)

stream = sc.resolve_stream("https://soundcloud.com/acidkid/track-slug")
```

---

## Downloads

Download methods are available on `SoundCloudAPI`, `SoundCloudYTDLP`, and `SoundCloud`
(the orchestrator).  `SoundCloudHTML` does **not** expose download methods.

`SoundCloudAPI.download_*` uses pure `requests` — no yt-dlp required.
`SoundCloudYTDLP.download_*` uses yt-dlp: `pip install nuvem_de_som[yt-dlp]`.

`SoundCloud` (orchestrator) tries the API backend first, falls back to yt-dlp.

`download_track()` returns `None` on failure (not a placeholder path).
`download_tracks()` returns only the paths of successfully downloaded files.

```python
from nuvem_de_som import SoundCloud, SoundCloudYTDLP

sc = SoundCloud()        # orchestrator — API first, yt-dlp fallback

# Single track → ~/Music/Artist - Title.mp3
path = sc.download_track(
    "https://soundcloud.com/acidkid/some-track",
    output_dir="~/Music",
)

# Multiple tracks — only successful downloads in the return list
paths = sc.download_tracks(
    ["https://soundcloud.com/acidkid/track-a",
     "https://soundcloud.com/acidkid/track-b"],
    output_dir="~/Music",
)

# Full artist page or set → ~/Music/Piratech/Title.mp3
sc.download_playlist("https://soundcloud.com/acidkid", output_dir="~/Music")
sc.download_playlist("https://soundcloud.com/acidkid/sets/beathop", output_dir="~/Music")
```

---

## Return types

### Release (tracks and sets)

Returned by `search_tracks`, `get_tracks`, `resolve_track`, `search_sets`.

| Attribute | Type | Description |
|---|---|---|
| `release.uri` | `str` | SoundCloud permalink |
| `release.image` | `str` | Artwork URL (`""` when unavailable) |
| `release.stream_mode` | `StreamMode` | Always `StreamMode.ON_DEMAND` |
| `release.work.title` | `str` | Track or set title |
| `release.work.media_type` | `MediaType` | Always `MediaType.MUSIC` |
| `release.work.runtime` | `float \| None` | Duration in seconds |
| `release.work.credits` | `list[Credit]` | Empty when artist unknown |
| `release.work.credits[0].entity.name` | `str` | Artist display name |
| `release.work.extra.get("artist_url")` | `str` | Artist profile URL |
| `release.work.external_ids` | `dict` | `soundcloud_track_id`, `soundcloud_user_id` |
| `release.external_ids` | `dict` | `soundcloud_playlist_id` (sets only) |

### Entity (artists / users)

Returned by `search_people`, `resolve_user`.

| Attribute | Type | Description |
|---|---|---|
| `entity.name` | `str` | Display name |
| `entity.kind` | `EntityKind` | Always `EntityKind.PERSON` |
| `entity.extra.get("artist_url")` | `str` | Profile URL |
| `entity.extra.get("image")` | `str` | Avatar URL |
| `entity.external_ids` | `dict` | `soundcloud_user_id` |

> `SoundCloudHTML.search_*` methods return empty credits, `""` image, and
> `None` runtime — those fields are absent from SoundCloud's search HTML.
> `get_tracks()` on an artist/set page provides all fields.

---

## Stream resolution

`resolve_stream(track_url, prefer="progressive")` resolves a permalink to a
direct audio URL.

- `prefer="progressive"` — direct MP3/AAC, seekable (default)
- `prefer="hls"` — HLS playlist (`.m3u8`)

Any value other than `"progressive"` or `"hls"` raises `ValueError`.

```python
url = sc.resolve_stream("https://soundcloud.com/acidkid/nuclear-chill")
url = sc.resolve_stream("...", prefer="hls")
```

## Logging

The library logs debug-level messages via the standard `logging` module under
the `nuvem_de_som` logger.  Enable with:

```python
import logging
logging.getLogger("nuvem_de_som").setLevel(logging.DEBUG)
```

---

## Terminal app — `nds`

Install the CLI extra to get the `nds` command:

```bash
pip install "nuvem_de_som[cli]"
# or with yt-dlp support:
pip install "nuvem_de_som[yt-dlp,cli]"
```

### Commands

#### `nds search QUERY`

Search SoundCloud and browse results interactively.  Results are shown as a
numbered list with artist and duration.  Type a number to select a track, then
choose `[p]lay`, `[d]ownload`, or `[b]ack`.

```bash
nds search "nuclear chill"
nds search "acidkid" --people          # search artists
nds search "chill" --sets              # search playlists
nds search "chill" --limit 50
```

#### `nds browse URL`

Load all tracks from an artist profile or set page and browse interactively.

```bash
nds browse https://soundcloud.com/acidkid
nds browse https://soundcloud.com/acidkid/sets/beathop --limit 100
```

#### `nds play URL`

Resolve a track URL to a direct stream and play it immediately.

```bash
nds play https://soundcloud.com/acidkid/piratech-nuclear-chill
```

#### `nds download URL`

Download a single track or a full playlist to disk.

```bash
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill -o ~/Music
nds download https://soundcloud.com/acidkid --playlist -o ~/Music
```

### Backend selection

All commands accept `--backend` / `-b`:

```bash
nds --backend api    search "chill"   # SoundCloudAPI  (default)
nds --backend html   search "chill"   # SoundCloudHTML
nds --backend ytdlp  search "chill"   # SoundCloudYTDLP
nds --backend auto   search "chill"   # SoundCloud orchestrator
```

### Playback

`nds play` and the interactive `[p]lay` action resolve the stream URL and pass
it to an audio player.  Specify any binary name or full path via `--player` or
the `NDS_PLAYER` environment variable:

```bash
nds --player mpv play <url>
nds --player /data/data/com.termux/files/usr/bin/mpv play <url>   # Termux
NDS_PLAYER="C:\Program Files\mpv\mpv.exe" nds play <url>          # Windows
NDS_PLAYER=vlc nds search "chill"
```

When neither is set, `nds` auto-detects the first available player from:
**mpv** → vlc → ffplay → mplayer → afplay (macOS) → cvlc.

Any binary that accepts a URL as its sole argument will work even if it is not
on the known list — `nds` will call `<player> <stream_url>` directly.
