# CLI reference: `nds`

Needs `pip install "nuvem_de_som[cli]"`.

## Global options

```bash
nds [--backend BACKEND] [--player PLAYER] COMMAND ...
```

| Option | Default | Description |
|---|---|---|
| `--backend` / `-b` | `auto` | `auto` `api` `html` `ytdlp` |
| `--player` | auto-detect | Player binary name or full path. Also read from the `NDS_PLAYER` environment variable. |

Backend mapping: `auto` maps to `SoundCloud`, `api` to `SoundCloudAPI`,
`html` to `SoundCloudHTML`, and `ytdlp` to `SoundCloudYTDLP`.

---

## nds search

```bash
nds search QUERY [--limit N] [--tracks | --people | --sets]
```

The default is `--tracks`. `nds search` shows a numbered list. Type a
number to select an item, then `[p]lay`, `[d]ownload`, or `[b]ack`. Type
`q` to quit.

```bash
nds search "nuclear chill"
nds search "acidkid" --people
nds search "chill mixes" --sets
nds search "lo-fi" --limit 50
```

---

## nds browse

```bash
nds browse URL [--limit N]
```

`nds browse` loads all tracks from an artist profile or set URL (default
limit 50) and enters the same interactive session as `search`.

```bash
nds browse https://soundcloud.com/acidkid
nds browse https://soundcloud.com/acidkid/sets/beathop --limit 100
```

---

## nds play

```bash
nds play URL
```

`nds play` resolves a track URL to a direct stream and passes it to the
audio player.

```bash
nds play https://soundcloud.com/acidkid/piratech-nuclear-chill
nds --player mpv play https://soundcloud.com/acidkid/piratech-nuclear-chill
```

---

## nds download

```bash
nds download URL [-o OUTPUT_DIR] [--playlist]
```

| Option | Default | Description |
|---|---|---|
| `-o` / `--output-dir` | `.` | Destination directory |
| `--playlist` / `-p` | off | Treat the URL as an artist or set page, and download all tracks |

```bash
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill -o ~/Music
nds download https://soundcloud.com/acidkid --playlist -o ~/Music
```

---

## Playback

When `--player` and `NDS_PLAYER` are both unset, `nds` auto-detects a
player in this order:

**mpv**, vlc, ffplay, mplayer, afplay (macOS), cvlc

Any binary that accepts a URL as its argument works, even if it is not on
this list.

```bash
NDS_PLAYER=mpv nds play <url>
NDS_PLAYER=/data/data/com.termux/files/usr/bin/mpv nds play <url>
NDS_PLAYER="C:\Program Files\mpv\mpv.exe" nds play <url>
```

`nds` applies player-specific flags automatically:

| Player | Flags |
|---|---|
| `mpv` | `--no-video --really-quiet` |
| `vlc` / `cvlc` | `--intf dummy --play-and-exit` |
| `ffplay` | `-nodisp -autoexit -loglevel quiet` |
| `mplayer` | `-really-quiet` |
| `afplay` | (URL only, macOS built-in, local files only) |
| anything else | URL as sole argument |

---
[← Transport](transport.md) · [Home](../README.md) · [API extras →](api.md)
