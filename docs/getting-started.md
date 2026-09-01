# Getting started

## Install

```bash
pip install nuvem_de_som                    # search + stream (requests + beautifulsoup4)
pip install "nuvem_de_som[stealth]"         # adds curl_cffi for browser-impersonating HTTP
pip install "nuvem_de_som[yt-dlp]"          # adds yt-dlp for downloads and stream fallback
pip install "nuvem_de_som[cli]"             # adds nds terminal app (click)
pip install "nuvem_de_som[yt-dlp,cli]"      # everything
```

## Pick a backend

```python
from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP

sc = SoundCloud()        # orchestrator: tries API, then yt-dlp, then HTML
sc = SoundCloudAPI()     # recommended for most tasks
sc = SoundCloudHTML()    # no extra deps; search returns title+URL only
sc = SoundCloudYTDLP()   # pip install nuvem_de_som[yt-dlp]
```

See [Backends reference](backends.md) for a full comparison.

## Search tracks

```python
for release in sc.search_tracks("nuclear chill", limit=10):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.work.runtime)
```

`search_tracks` returns `mediavocab.Release` objects. See
[mediavocab converters](converters.md) for the full field list.

## Get all tracks for an artist or set

```python
for release in sc.get_tracks("https://soundcloud.com/acidkid", limit=200):
    print(release.work.title, release.uri)

for release in sc.get_tracks("https://soundcloud.com/acidkid/sets/beathop"):
    print(release.work.title)
```

## Resolve a stream URL

```python
# Direct MP3/AAC (seekable)
url = sc.resolve_stream("https://soundcloud.com/acidkid/piratech-nuclear-chill")

# HLS playlist
url = sc.resolve_stream("...", prefer="hls")
```

`SoundCloudHTML.resolve_stream()` raises `NotImplementedError`. Use
`SoundCloudAPI` or `SoundCloudYTDLP` for stream access.

## Download

```python
path = sc.download_track("https://soundcloud.com/acidkid/some-track", output_dir="~/Music")
sc.download_playlist("https://soundcloud.com/acidkid", output_dir="~/Music")
```

`SoundCloudHTML` has no download methods. See [Backends reference](backends.md).

## Discover artists with crawl()

`SoundCloudAPI.crawl()` walks the social graph (followers and followings)
with a breadth-first search from one or more seed profiles. A seed can be a
profile URL or a keyword query string. A keyword seed resolves to the top
`search_people` result.

```python
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()
seen = set()
for entity in sc.crawl(
    ["https://soundcloud.com/noisia", "black metal"],
    social_depth=20,
    max_artists=100,
    seen=seen,
):
    followers = entity.extra.get("followers_count", "?")
    verified  = " verified" if entity.extra.get("verified") else ""
    print(entity.name, followers, verified)
```

Pass the same `seen` set across calls to resume without visiting the same
profile twice. `SoundCloudHTML` and `SoundCloudYTDLP` also expose `crawl()`,
but they use a flat expansion, not a follower graph, because those backends
have no follower endpoints.

See `examples/11_crawl.py` and `examples/12_followers.py` for more.

## Logging

```python
import logging
logging.getLogger("nuvem_de_som").setLevel(logging.DEBUG)
```

---
[Home](../README.md) · [Backends reference →](backends.md)
