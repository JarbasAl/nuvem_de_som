# CLI reference — `nds`

Requires `pip install "nuvem_de_som[cli]"`.

## Global options

```
nds [--backend BACKEND] [--player PLAYER] COMMAND ...
```

| Option | Default | Description |
|---|---|---|
| `--backend` / `-b` | `auto` | `auto` `api` `html` `ytdlp` |
| `--player` | auto-detect | Player binary name or full path. Also read from `NDS_PLAYER` env var. |

Backend mapping: `auto` → `SoundCloud`, `api` → `SoundCloudAPI`, `html` →
`SoundCloudHTML`, `ytdlp` → `SoundCloudYTDLP`.

---

## nds search

```bash
nds search QUERY [--limit N] [--tracks | --people | --sets]
```

Default: `--tracks`. Shows a numbered list; type a number to select, then
`[p]lay`, `[d]ownload`, or `[b]ack`. Type `q` to quit.

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

Loads all tracks from an artist profile or set URL (default limit 50) and
enters the same interactive session as `search`.

```bash
nds browse https://soundcloud.com/acidkid
nds browse https://soundcloud.com/acidkid/sets/beathop --limit 100
```

---

## nds play

```bash
nds play URL
```

Resolves a track URL to a direct stream and passes it to the audio player.

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
| `--playlist` / `-p` | off | Treat URL as artist/set page, download all tracks |

```bash
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill
nds download https://soundcloud.com/acidkid/piratech-nuclear-chill -o ~/Music
nds download https://soundcloud.com/acidkid --playlist -o ~/Music
```

---

## Playback

Auto-detect order when `--player` / `NDS_PLAYER` are not set:

**mpv** → vlc → ffplay → mplayer → afplay (macOS) → cvlc

Any binary that accepts a URL as its argument works, even if not on this list.

```bash
NDS_PLAYER=mpv nds play <url>
NDS_PLAYER=/data/data/com.termux/files/usr/bin/mpv nds play <url>
NDS_PLAYER="C:\Program Files\mpv\mpv.exe" nds play <url>
```

Player-specific flags applied automatically:

| Player | Flags |
|---|---|
| `mpv` | `--no-video --really-quiet` |
| `vlc` / `cvlc` | `--intf dummy --play-and-exit` |
| `ffplay` | `-nodisp -autoexit -loglevel quiet` |
| `mplayer` | `-really-quiet` |
| `afplay` | (URL only — macOS built-in, local files only) |
| anything else | URL as sole argument |
