# nuvem-de-som

SoundCloud search, stream, and download client. Three independent backends, one
orchestrator, one terminal app. Returns
[`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release` and
`Entity` objects for typed, structured metadata.

## Install

```bash
pip install nuvem_de_som           # search + stream (no yt-dlp)
pip install "nuvem_de_som[yt-dlp]" # adds yt-dlp for download & stream fallback
pip install "nuvem_de_som[cli]"    # adds the nds terminal app
pip install "nuvem_de_som[yt-dlp,cli]"  # everything
pip install "nuvem_de_som[stealth]"     # adds curl_cffi for browser-impersonating HTTP
```

### Stealth transport (`curl_cffi`)

SoundCloud's API and HTML endpoints are increasingly bot-defended (TLS/JA3 and
HTTP/2 fingerprinting). To preempt blocks, install the `[stealth]` extra and
opt in via env var:

```bash
pip install "nuvem_de_som[stealth]"
NUVEM_TRANSPORT=curl_cffi python -m yourapp
```

When `NUVEM_TRANSPORT=curl_cffi` is set and `curl_cffi` is importable,
`SoundCloudAPI`, `SoundCloudHTML`, and the `SoundCloud` orchestrator default
to a `curl_cffi.requests.Session(impersonate="chrome")` for every request.
Otherwise they fall back transparently to the stdlib `requests.Session`.

You can also inject any compatible session directly:

```python
from curl_cffi import requests as cffi_requests
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI(session=cffi_requests.Session(impersonate="chrome120"))
```

Note: `SoundCloudYTDLP` uses yt-dlp internally for its HTTP traffic and does
**not** honour an injected session — yt-dlp manages its own networking.

## Terminal app — `nds`

```bash
nds search "nuclear chill"          # interactive: pick a track, then play or download
nds browse https://soundcloud.com/acidkid   # browse artist page interactively
nds play   https://soundcloud.com/acidkid/piratech-nuclear-chill
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill -o ~/Music
nds download https://soundcloud.com/acidkid --playlist -o ~/Music

nds --backend api search "chill"    # force a specific backend (api/html/ytdlp/auto)
```

Playback uses `--player` / `NDS_PLAYER` env var, or auto-detects: **mpv** → vlc → ffplay → mplayer → afplay → cvlc.
Any binary name or full path works — Termux, Windows, macOS all supported.

## Python API — quick start

```python
from nuvem_de_som import SoundCloud

sc = SoundCloud()   # orchestrator: API → yt-dlp → HTML

# Search tracks → mediavocab.Release objects
for release in sc.search_tracks("nuclear chill", limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.work.runtime)  # runtime in seconds

# Browse an artist or set page
for release in sc.get_tracks("https://soundcloud.com/acidkid", limit=50):
    print(release.work.title, release.uri)

# Search artists → mediavocab.Entity objects
for entity in sc.search_people("acidkid", limit=5):
    print(entity.name, entity.extra.get("artist_url"))

# Resolve a direct stream URL (no yt-dlp)
url = sc.resolve_stream("https://soundcloud.com/acidkid/piratech-nuclear-chill")
url = sc.resolve_stream("...", prefer="hls")   # or "progressive" (default)

# Download — SoundCloudAPI uses pure requests; SoundCloudYTDLP uses yt-dlp
path = sc.download_track("https://soundcloud.com/acidkid/piratech-nuclear-chill",
                          output_dir="~/Music")
sc.download_playlist("https://soundcloud.com/acidkid", output_dir="~/Music")
```

### Return types at a glance

**`Release`** — from `search_tracks`, `get_tracks`, `resolve_track`, `search_sets`:

```python
release.uri                          # SoundCloud permalink
release.image                        # artwork URL
release.work.title                   # track title
release.work.runtime                 # duration in seconds (float or None)
release.work.credits[0].entity.name  # artist display name (if available)
release.work.extra.get("artist_url") # artist profile URL
release.work.external_ids            # {"soundcloud_track_id": "...", "soundcloud_user_id": "..."}
release.work.aka                     # [permalink slug]
release.work.content_genres          # ["electronic", "ambient", ...]   from genre + tag_list
release.work.production_country      # ISO 3166 alpha-2 of the uploader, when known
release.work.tracklist               # [Appearance, ...] for sets/playlists
release.codec                        # e.g. "audio/mpeg"
release.bitrate                      # "128" (sq) / "256" (hq) when known
release.audio_channels               # "stereo"
release.license                      # SPDX id ("CC-BY-NC-4.0", "CC0-1.0") or raw
release.release_date                 # ISO date validated by mediavocab
```

For SoundCloud sets/playlists, `Work.tracklist` is populated with typed
`mediavocab.Appearance` entries (each carrying the per-track `Work`),
positioned 1..N. See `examples/set_tracklist.py`.

**`Entity`** — from `search_people`, `resolve_user`:

```python
entity.name                          # display name
entity.extra.get("artist_url")       # profile URL
entity.extra.get("image")            # avatar URL
entity.external_ids                  # {"soundcloud_user_id": "..."}
```

## Backends

| Backend | Search | Stream | Download | Extra dep |
|---|---|---|---|---|
| `SoundCloudAPI` | full metadata | progressive or HLS | pure requests | — |
| `SoundCloudHTML` | title+URL only | raises `NotImplementedError` | — | — |
| `SoundCloudYTDLP` | full metadata | yt-dlp | yt-dlp | `yt-dlp` |
| `SoundCloud` | API → yt-dlp → HTML | API first, yt-dlp fallback | API first, yt-dlp fallback | optional `yt-dlp` |

Use a concrete class when you need a specific backend; use `SoundCloud` for resilience.

```python
from nuvem_de_som import SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP, SoundCloud

sc = SoundCloudAPI()     # recommended — full metadata, no yt-dlp
sc = SoundCloudHTML()    # no extra deps, title+URL from search pages
sc = SoundCloudYTDLP()   # yt-dlp backed, slowest but most resilient
sc = SoundCloud()        # tries all three in order
```

## Transport — stealth mode

SoundCloud fingerprints TLS and HTTP/2 frames. Set `NUVEM_TRANSPORT=curl_cffi`
and install the `[stealth]` extra to impersonate a real browser:

```bash
NUVEM_TRANSPORT=curl_cffi python myscript.py
```

Or inject a session directly:

```python
from curl_cffi import requests as cffi_requests
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI(session=cffi_requests.Session(impersonate="chrome120"))
```

`SoundCloudYTDLP` manages its own networking and ignores an injected session.

## mediavocab integration

All track methods return `mediavocab.Release`; people methods return
`mediavocab.Entity`. No conversion step needed.

```python
release = sc.resolve_track("https://soundcloud.com/acidkid/piratech-nuclear-chill")

release.uri                          # SoundCloud permalink
release.image                        # artwork URL
release.work.title                   # track title
release.work.runtime                 # duration in seconds (float or None)
release.work.credits[0].entity.name  # artist display name
release.work.content_genres          # ["electronic", "ambient", ...]
release.work.external_ids            # {"soundcloud_track_id": "...", ...}
release.codec                        # "audio/mpeg"
release.bitrate                      # "128" or "256"
release.license                      # SPDX id e.g. "CC-BY-NC-4.0"
release.release_date                 # ISO date "2018-09-25"
```

## CLI — `nds`

```bash
nds search "nuclear chill"
nds search "acidkid" --people
nds browse https://soundcloud.com/acidkid
nds play   https://soundcloud.com/acidkid/piratech-nuclear-chill
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill -o ~/Music
nds download https://soundcloud.com/acidkid --playlist -o ~/Music

nds --backend api    search "chill"   # force backend: api / html / ytdlp / auto
NDS_PLAYER=vlc nds play <url>         # override player; auto-detects mpv → vlc → ffplay
```

## Docs

- [Getting started](docs/getting-started.md)
- [Backends reference](docs/backends.md)
- [Streams and transcodings](docs/streams.md)
- [mediavocab converters](docs/converters.md)
- [Transport](docs/transport.md)
- [CLI reference](docs/cli.md)

## Examples

See [`examples/`](examples/) — numbered zero-to-hero scripts.

## License

Apache 2.0
