"""nds — nuvem_de_som terminal client.

Browse and play SoundCloud from the terminal::

    nds search "nuclear chill"
    nds browse https://soundcloud.com/acidkid
    nds play   https://soundcloud.com/acidkid/piratech-nuclear-chill
    nds download https://soundcloud.com/acidkid/piratech-nuclear-chill

Set NDS_PLAYER to override the audio player, e.g.::

    NDS_PLAYER=mpv nds play ...
    NDS_PLAYER=/data/data/com.termux/files/usr/bin/mpv nds play ...
    NDS_PLAYER="C:\\Program Files\\mpv\\mpv.exe" nds play ...
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Optional

try:
    import click
except ImportError:
    click = None  # type: ignore[assignment]

from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudHTML, SoundCloudYTDLP


def _track_view(t) -> dict:
    """Normalise a track (Release object or dict) into a flat view dict.

    The CLI was originally written against raw track dicts; backends now
    return mediavocab.Release objects. This adapter lets the rest of the
    CLI keep the simple dict idiom while accepting both shapes.
    """
    if isinstance(t, dict):
        return t
    credits = getattr(getattr(t, "work", None), "credits", None) or []
    artist = credits[0].entity.name if credits else ""
    runtime = getattr(getattr(t, "work", None), "runtime", None)
    duration = int(runtime) if runtime is not None else None
    return {
        "title": getattr(getattr(t, "work", None), "title", "") or "",
        "url": getattr(t, "uri", "") or "",
        "artist": artist,
        "duration": duration,
    }


def _entity_view(p) -> dict:
    """Normalise a person (Entity object or dict) into a flat view dict."""
    if isinstance(p, dict):
        return p
    return {
        "artist": getattr(p, "name", "") or "",
        "artist_url": (getattr(p, "extra", {}) or {}).get("artist_url", ""),
    }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKENDS = {
    "auto": SoundCloud,
    "api": SoundCloudAPI,
    "html": SoundCloudHTML,
    "ytdlp": SoundCloudYTDLP,
}

# Candidates tried in order when --player / NDS_PLAYER are not set.
# Any binary name or absolute path works — shutil.which handles both.
_DEFAULT_PLAYERS = ["mpv", "vlc", "ffplay", "mplayer", "afplay", "cvlc"]


def _resolve_player(player_hint: Optional[str]) -> Optional[str]:
    """Return the full path to an audio player binary, or None."""
    candidates = [player_hint] if player_hint else _DEFAULT_PLAYERS
    for p in candidates:
        found = shutil.which(p)
        if found:
            return found
    return None


def _play_url(player_path: str, stream_url: str) -> None:
    """Launch *player_path* with *stream_url*.  Unknown players get just the URL."""
    name = os.path.basename(player_path).lower()
    # Strip .exe suffix on Windows
    name = name.removesuffix(".exe") if hasattr(name, "removesuffix") else (
        name[:-4] if name.endswith(".exe") else name
    )
    if name == "mpv":
        args = [player_path, "--no-video", "--really-quiet", stream_url]
    elif name in ("vlc", "cvlc"):
        args = [player_path, "--intf", "dummy", "--play-and-exit", stream_url]
    elif name == "ffplay":
        args = [player_path, "-nodisp", "-autoexit", "-loglevel", "quiet", stream_url]
    elif name == "afplay":
        # macOS built-in — requires a local file, so this path is best-effort
        args = [player_path, stream_url]
    elif name == "mplayer":
        args = [player_path, "-really-quiet", stream_url]
    else:
        # Unknown player: pass the URL as the sole argument and hope for the best
        args = [player_path, stream_url]
    subprocess.run(args)


def _fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _print_tracks(tracks: List[dict], offset: int = 0) -> None:
    width = shutil.get_terminal_size().columns
    for i, raw in enumerate(tracks, start=offset + 1):
        t = _track_view(raw)
        dur = _fmt_duration(t.get("duration"))
        artist = t.get("artist") or ""
        title = t.get("title") or t.get("url", "")
        label = f"  {i:>3}. {title}"
        if artist:
            label += f"  [{artist}]"
        right = f"  {dur}"
        pad = width - len(label) - len(right)
        label += (" " * pad + right) if pad > 0 else right
        click.echo(label)


def _print_people(people: List[dict], offset: int = 0) -> None:
    for i, raw in enumerate(people, start=offset + 1):
        p = _entity_view(raw)
        name = p.get("artist") or ""
        url = p.get("artist_url") or ""
        click.echo(f"  {i:>3}. {name}  <{url}>")


def _resolve_stream(sc, track_url: str) -> Optional[str]:
    try:
        return sc.resolve_stream(track_url)
    except NotImplementedError:
        return SoundCloudAPI().resolve_stream(track_url)


def _resolve_and_play(sc, track_url: str, player_hint: Optional[str]) -> None:
    player_path = _resolve_player(player_hint)
    if not player_path:
        hint = f" (tried: {player_hint!r})" if player_hint else ""
        click.echo(f"No audio player found{hint}. "
                   "Install mpv/vlc/ffplay or set --player.", err=True)
        return
    click.echo("Resolving stream …")
    stream_url = _resolve_stream(sc, track_url)
    if not stream_url:
        click.echo("Could not resolve a stream URL.", err=True)
        return
    click.echo(f"Playing via {player_path} …")
    _play_url(player_path, stream_url)


# ---------------------------------------------------------------------------
# Interactive session — used by search and browse
# ---------------------------------------------------------------------------

def _interactive_session(sc, tracks: List[dict], people: List[dict],
                         title: str, player_hint: Optional[str]) -> None:
    if not tracks and not people:
        click.echo("No results.")
        return

    click.echo(f"\n{title}")
    if people:
        click.echo("\nArtists:")
        _print_people(people)
    if tracks:
        click.echo("\nTracks:")
        _print_tracks(tracks)

    while True:
        click.echo()
        choice = click.prompt(
            "Enter track # to select, 'q' to quit",
            default="q", show_default=False,
        ).strip().lower()

        if choice in ("q", "quit", "exit", ""):
            break

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(tracks)):
                click.echo("Number out of range.")
                continue
        except ValueError:
            click.echo("Type a number or 'q'.")
            continue

        track = _track_view(tracks[idx])
        click.echo(f"\n  {track['title']}  [{track.get('artist', '')}]  "
                   f"{_fmt_duration(track.get('duration'))}")
        click.echo("  [p]lay  [d]ownload  [b]ack")
        action = click.prompt("  Action", default="p", show_default=False).strip().lower()

        if action in ("p", "play"):
            _resolve_and_play(sc, track["url"], player_hint)
        elif action in ("d", "download"):
            out = click.prompt("  Output dir", default=".", show_default=True)
            try:
                path = sc.download_track(track["url"], output_dir=out)
                if path:
                    click.echo(f"  Saved: {path}")
                else:
                    click.echo(f"  Failed to save: {track['url']}", err=True)
            except Exception as exc:
                click.echo(f"  Download failed: {exc}", err=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.group()
@click.option("--backend", "-b",
              type=click.Choice(list(BACKENDS)), default="auto", show_default=True,
              help="Which backend to use.")
@click.option("--player", "player_hint", default=None, show_default=False,
              envvar="NDS_PLAYER",
              help="Audio player binary name or full path (env: NDS_PLAYER). "
                   "Falls back to auto-detection: mpv, vlc, ffplay, mplayer.")
@click.pass_context
def cli(ctx: click.Context, backend: str, player_hint: Optional[str]) -> None:
    """nds — browse and play SoundCloud from the terminal."""
    ctx.ensure_object(dict)
    ctx.obj["sc"] = BACKENDS[backend]()
    ctx.obj["player"] = player_hint


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=25, show_default=True, help="Max results.")
@click.option("--people", "mode", flag_value="people", help="Search artists.")
@click.option("--sets", "mode", flag_value="sets", help="Search playlists/sets.")
@click.option("--tracks", "mode", flag_value="tracks", default=True,
              help="Search tracks (default).")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int, mode: str) -> None:
    """Search SoundCloud and browse results interactively."""
    sc = ctx.obj["sc"]
    player = ctx.obj["player"]

    if mode == "people":
        _print_people(list(sc.search_people(query, limit=limit)))
        return

    if mode == "sets":
        sets = list(sc.search_sets(query, limit=limit))
        if not sets:
            click.echo("No sets found.")
            return
        for i, raw in enumerate(sets, 1):
            s = _track_view(raw)
            click.echo(f"  {i:>3}. {s['title']}  [{s.get('artist', '')}]  <{s['url']}>")
        return

    click.echo(f"Searching for '{query}' …")
    tracks = list(sc.search_tracks(query, limit=limit))
    _interactive_session(sc, tracks, [], f"Results for '{query}'", player)


# ---------------------------------------------------------------------------
# browse
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--limit", "-n", default=50, show_default=True,
              help="Max tracks to load.")
@click.pass_context
def browse(ctx: click.Context, url: str, limit: int) -> None:
    """Browse an artist or set page interactively."""
    sc = ctx.obj["sc"]
    player = ctx.obj["player"]
    click.echo(f"Loading {url} …")
    tracks = list(sc.get_tracks(url, limit=limit))
    _interactive_session(sc, tracks, [], url, player)


# ---------------------------------------------------------------------------
# play
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.pass_context
def play(ctx: click.Context, url: str) -> None:
    """Play a track URL directly."""
    _resolve_and_play(ctx.obj["sc"], url, ctx.obj["player"])


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--output-dir", "-o", default=".", show_default=True,
              help="Directory to save the file.")
@click.option("--playlist", "-p", is_flag=True,
              help="Treat URL as artist/set page and download all tracks.")
@click.pass_context
def download(ctx: click.Context, url: str, output_dir: str, playlist: bool) -> None:
    """Download a track (or full playlist) to disk."""
    sc = ctx.obj["sc"]
    if playlist:
        click.echo(f"Downloading playlist {url} → {output_dir}")
        try:
            sc.download_playlist(url, output_dir=output_dir)
        except Exception as exc:
            click.echo(f"Playlist download failed: {exc}", err=True)
            sys.exit(1)
    else:
        click.echo(f"Downloading {url} → {output_dir}")
        path = sc.download_track(url, output_dir=output_dir)
        if path:
            click.echo(f"Saved: {path}")
        else:
            click.echo("Download failed.", err=True)
            sys.exit(1)


def main() -> None:
    if click is None:
        print("nds requires click: pip install \"nuvem_de_som[cli]\"", file=sys.stderr)
        sys.exit(1)
    cli(obj={})


if __name__ == "__main__":
    main()
