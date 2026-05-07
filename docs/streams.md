# Streams and transcodings

## resolve_stream

```python
url = sc.resolve_stream(track_url, prefer="progressive")
url = sc.resolve_stream(track_url, prefer="hls")
```

`prefer` accepts only `"progressive"` or `"hls"`. Any other value raises `ValueError`.

Returns the direct audio URL as a string, or `None` when resolution fails.

### SoundCloudAPI path

`SoundCloudAPI.resolve_stream` — `nuvem_de_som/__init__.py:603`

1. Calls `GET /resolve?url=<track_url>` to get the track JSON.
2. Reads `media.transcodings[]`, sorts by: preferred protocol first, then any.
3. For each transcoding entry, calls `GET <transcoding.url>?client_id=<cid>`.
4. Returns the `url` field from the first successful response.

No yt-dlp involved at any point.

### SoundCloudYTDLP path

`SoundCloudYTDLP.resolve_stream` — `nuvem_de_som/__init__.py:1108`

Runs `yt_dlp.YoutubeDL.extract_info(track_url)` without downloading, then
walks `info["formats"]` in reverse (highest quality last). Maps:

- `prefer="progressive"` → `format.protocol == "https"`
- `prefer="hls"` → `format.protocol == "m3u8_native"`

Falls back to the last format entry or `info["url"]` if no match.

### SoundCloudHTML

`resolve_stream` raises `NotImplementedError`. SoundCloud's signed stream
URLs are not present in page HTML.

---

## _parse_transcodings — codec and bitrate on Release

`_parse_transcodings` — `nuvem_de_som/__init__.py:150`

Called by `SoundCloudAPI._parse_track` on the `media.transcodings[]` array from
the API. Returns `(codec, bitrate)`:

1. Filters to `protocol == "progressive"` entries; if none exist, uses all.
2. Sorts by `quality`: `hq` (0) before `sq` (1) before anything else.
3. From the best entry: `codec = format.mime_type` (e.g. `"audio/mpeg"`),
   `bitrate = "256"` for `hq` or `"128"` for `sq`.

These values populate `Release.codec`, `Release.bitrate`, and
`Release.audio_channels` (`"stereo"` whenever a codec is known, `""` otherwise).

## Progressive vs HLS

| Type | `prefer=` | Format | Seekable | Notes |
|---|---|---|---|---|
| Progressive | `"progressive"` | MP3 / AAC direct URL | Yes | Default |
| HLS | `"hls"` | `.m3u8` playlist | Player-dependent | Useful for live/DRM content |

SoundCloud serves most tracks with both. Progressive is the default and works
directly in any HTTP-capable media player.
