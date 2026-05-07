# nuvem-de-som

SoundCloud search, stream, and download client. Three independent backends, one
orchestrator, one terminal app. Returns
[`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release` and
`Entity` objects.

## Install

```bash
pip install nuvem_de_som                    # search + stream
pip install "nuvem_de_som[stealth]"         # + curl_cffi browser impersonation
pip install "nuvem_de_som[yt-dlp]"          # + yt-dlp for downloads & stream fallback
pip install "nuvem_de_som[cli]"             # + nds terminal app
pip install "nuvem_de_som[yt-dlp,cli]"      # everything
```

## Quick start

```python
from nuvem_de_som import SoundCloud

sc = SoundCloud()   # orchestrator: API → yt-dlp → HTML

for release in sc.search_tracks("nuclear chill", limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.work.runtime)  # runtime in seconds

stream_url = sc.resolve_stream("https://soundcloud.com/acidkid/piratech-nuclear-chill")
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
