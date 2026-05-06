# nuvem_de_som

SoundCloud search, stream, and download client. Three independent backends, one orchestrator, one terminal app.

Returns [`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release` and `Entity` objects for typed, structured metadata.

## Install

```bash
pip install nuvem_de_som           # search + stream (no yt-dlp)
pip install "nuvem_de_som[yt-dlp]" # adds yt-dlp for download & stream fallback
pip install "nuvem_de_som[cli]"    # adds the nds terminal app
pip install "nuvem_de_som[yt-dlp,cli]"  # everything
```

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
from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP

sc = SoundCloud()        # orchestrator: API → yt-dlp → HTML fallback (recommended)
sc = SoundCloudAPI()     # API only — full metadata, no yt-dlp required
sc = SoundCloudHTML()    # HTML scraper — no extra deps
sc = SoundCloudYTDLP()   # yt-dlp only

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
```

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
| `SoundCloudAPI` | ✅ full metadata | ✅ | ✅ pure requests | — |
| `SoundCloudHTML` | ⚠️ title+URL only | ❌ | ❌ | — |
| `SoundCloudYTDLP` | ✅ | ✅ | ✅ yt-dlp | `yt-dlp` |
| `SoundCloud` | ✅ API→yt-dlp→HTML | ✅ | ✅ API first | optional `yt-dlp` |

> `SoundCloudHTML.search_*` returns only title + URL from SoundCloud's search HTML.
> Use `get_tracks()` on an artist/set page for full metadata, or `search_tracks_enriched()`
> for one extra request per result.

## Docs

- [Full API reference](docs/api.md)
