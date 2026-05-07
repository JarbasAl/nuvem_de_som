"""CLI tests using Click's CliRunner — fully offline.

Backends are stubbed out; we exercise option parsing, command branches,
and player resolution. The CLI's interactive helpers consume raw dicts
(legacy contract); search/browse with non-empty results currently flow
Release objects from backends into dict-expecting helpers and so are
not exercised here.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from mediavocab import (
    Entity, EntityKind,
)

from nuvem_de_som import cli as cli_module
from nuvem_de_som.cli import (
    BACKENDS, _entity_view, _fmt_duration, _interactive_session,
    _play_url, _print_people, _print_tracks, _resolve_and_play,
    _resolve_player, _resolve_stream, _track_view, cli, main,
)
from mediavocab import (
    Credit, CreditSection, EntityRef,
    MediaType, Release, RelationRole, StreamMode, Work,
)


def _make_release(title="T", artist="A", uri="https://soundcloud.com/a/t",
                  runtime=60.0):
    artist_ref = EntityRef(name=artist, kind=EntityKind.PERSON)
    credits = [Credit(entity=artist_ref, role="artist",
                      relation_role=RelationRole.PERFORMER,
                      section=CreditSection.PRINCIPAL)]
    work = Work(title=title, media_type=MediaType.MUSIC,
                runtime=runtime, credits=credits)
    return Release(work=work, uri=uri, stream_mode=StreamMode.ON_DEMAND)


def _make_entity(name="N", url="https://soundcloud.com/n"):
    return Entity(name=name, kind=EntityKind.PERSON,
                  extra={"artist_url": url})


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _track_dict(title="T", url="https://soundcloud.com/a/t",
                artist="A", duration=60):
    return {"title": title, "url": url, "artist": artist, "duration": duration}


def _people_dict(name="A", url="https://soundcloud.com/a"):
    return {"artist": name, "artist_url": url}


def _set_dict(title="S", url="https://soundcloud.com/a/sets/x", artist="A"):
    return {"title": title, "url": url, "artist": artist}


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------

class TestTrackEntityViews:
    def test_track_view_dict_passthrough(self):
        d = {"title": "x"}
        assert _track_view(d) is d

    def test_track_view_release(self):
        rel = _make_release(title="X", artist="Y", uri="u", runtime=90.0)
        v = _track_view(rel)
        assert v == {"title": "X", "url": "u", "artist": "Y", "duration": 90}

    def test_track_view_release_no_runtime(self):
        rel = _make_release(runtime=None)
        v = _track_view(rel)
        assert v["duration"] is None

    def test_entity_view_dict_passthrough(self):
        d = {"artist": "x", "artist_url": "u"}
        assert _entity_view(d) is d

    def test_entity_view_entity(self):
        ent = _make_entity(name="N", url="https://soundcloud.com/n")
        v = _entity_view(ent)
        assert v == {"artist": "N", "artist_url": "https://soundcloud.com/n"}


class TestFmtDuration:
    def test_none(self):
        assert _fmt_duration(None) == "--:--"

    def test_seconds_only(self):
        assert _fmt_duration(45) == "0:45"

    def test_minutes(self):
        assert _fmt_duration(125) == "2:05"

    def test_hours(self):
        assert _fmt_duration(3725) == "1:02:05"


# ---------------------------------------------------------------------------
# Player resolution
# ---------------------------------------------------------------------------

class TestResolvePlayer:
    def test_explicit_hint_found(self):
        with patch("nuvem_de_som.cli.shutil.which",
                   side_effect=lambda p: "/usr/bin/" + p if p == "mpv" else None):
            assert _resolve_player("mpv") == "/usr/bin/mpv"

    def test_explicit_hint_missing(self):
        with patch("nuvem_de_som.cli.shutil.which", return_value=None):
            assert _resolve_player("nope") is None

    def test_default_chain_picks_first(self):
        def which(p):
            return "/usr/bin/" + p if p == "vlc" else None
        with patch("nuvem_de_som.cli.shutil.which", side_effect=which):
            assert _resolve_player(None) == "/usr/bin/vlc"

    def test_none_found(self):
        with patch("nuvem_de_som.cli.shutil.which", return_value=None):
            assert _resolve_player(None) is None


class TestPlayUrl:
    def _run(self, path):
        with patch("nuvem_de_som.cli.subprocess.run") as run:
            _play_url(path, "https://stream/x.mp3")
        return run.call_args[0][0]

    def test_mpv(self):
        assert "--no-video" in self._run("/usr/bin/mpv")

    def test_vlc(self):
        assert "--play-and-exit" in self._run("/usr/bin/vlc")

    def test_cvlc(self):
        assert "--play-and-exit" in self._run("/usr/bin/cvlc")

    def test_ffplay(self):
        assert "-nodisp" in self._run("/usr/bin/ffplay")

    def test_afplay(self):
        assert self._run("/usr/bin/afplay") == ["/usr/bin/afplay",
                                                "https://stream/x.mp3"]

    def test_mplayer(self):
        assert "-really-quiet" in self._run("/usr/bin/mplayer")

    def test_unknown_player(self):
        assert self._run("/usr/bin/xyz") == ["/usr/bin/xyz",
                                             "https://stream/x.mp3"]

    def test_windows_exe_suffix(self):
        with patch("nuvem_de_som.cli.subprocess.run") as run:
            _play_url("C:/Program Files/mpv/mpv.exe", "u")
        assert "--no-video" in run.call_args[0][0]


# ---------------------------------------------------------------------------
# _resolve_stream / _resolve_and_play
# ---------------------------------------------------------------------------

class TestResolveStream:
    def test_uses_backend_resolve_stream(self):
        sc = MagicMock()
        sc.resolve_stream.return_value = "https://stream"
        assert _resolve_stream(sc, "u") == "https://stream"

    def test_falls_back_to_api_on_not_implemented(self):
        sc = MagicMock()
        sc.resolve_stream.side_effect = NotImplementedError
        with patch("nuvem_de_som.cli.SoundCloudAPI") as api_cls:
            api_cls.return_value.resolve_stream.return_value = "https://stream"
            assert _resolve_stream(sc, "u") == "https://stream"


class TestResolveAndPlay:
    def test_no_player(self):
        runner = CliRunner()
        with runner.isolation() as (out, err, _):
            with patch("nuvem_de_som.cli._resolve_player", return_value=None):
                _resolve_and_play(MagicMock(), "u", None)
        assert b"No audio player" in err.getvalue()

    def test_no_player_with_hint(self):
        runner = CliRunner()
        with runner.isolation() as (out, err, _):
            with patch("nuvem_de_som.cli._resolve_player", return_value=None):
                _resolve_and_play(MagicMock(), "u", "fakebin")
        assert b"fakebin" in err.getvalue()

    def test_unresolvable_stream(self):
        runner = CliRunner()
        sc = MagicMock()
        sc.resolve_stream.return_value = None
        with runner.isolation() as (out, err, _):
            with patch("nuvem_de_som.cli._resolve_player", return_value="/p"):
                _resolve_and_play(sc, "u", None)
        assert b"Could not resolve" in err.getvalue()

    def test_happy_path(self):
        runner = CliRunner()
        sc = MagicMock()
        sc.resolve_stream.return_value = "https://stream"
        with runner.isolation():
            with patch("nuvem_de_som.cli._resolve_player",
                       return_value="/usr/bin/mpv"):
                with patch("nuvem_de_som.cli._play_url") as play:
                    _resolve_and_play(sc, "u", None)
        play.assert_called_once_with("/usr/bin/mpv", "https://stream")


# ---------------------------------------------------------------------------
# _print_tracks / _print_people — dict input (the CLI's legacy contract)
# ---------------------------------------------------------------------------

class TestPrint:
    def test_print_tracks_dict(self):
        runner = CliRunner()
        with runner.isolation() as (out, _e, _x):
            _print_tracks([_track_dict(title="X", artist="Y", duration=65)])
        assert b"X" in out.getvalue()
        assert b"Y" in out.getvalue()

    def test_print_tracks_no_artist_no_duration(self):
        runner = CliRunner()
        with runner.isolation() as (out, _e, _x):
            _print_tracks([{"title": "T", "url": "u"}])
        assert b"T" in out.getvalue()

    def test_print_people(self):
        runner = CliRunner()
        with runner.isolation() as (out, _e, _x):
            _print_people([_people_dict(name="N",
                                        url="https://soundcloud.com/n")])
        assert b"N" in out.getvalue()


# ---------------------------------------------------------------------------
# _interactive_session — feeds dicts (legacy contract)
# ---------------------------------------------------------------------------

class TestInteractive:
    def test_no_results(self):
        runner = CliRunner()
        with runner.isolation() as (out, _e, _x):
            _interactive_session(MagicMock(), [], [], "title", None)
        assert b"No results" in out.getvalue()

    def test_quit_immediately(self):
        runner = CliRunner()
        sc = MagicMock()
        with runner.isolation(input="q\n") as (out, _e, _x):
            _interactive_session(sc, [_track_dict()], [_people_dict()],
                                 "title", None)
        assert b"Tracks" in out.getvalue()
        assert b"Artists" in out.getvalue()

    def test_invalid_number(self):
        runner = CliRunner()
        sc = MagicMock()
        with runner.isolation(input="abc\nq\n") as (out, _e, _x):
            _interactive_session(sc, [_track_dict()], [], "t", None)
        assert b"Type a number" in out.getvalue()

    def test_out_of_range(self):
        runner = CliRunner()
        sc = MagicMock()
        with runner.isolation(input="9\nq\n") as (out, _e, _x):
            _interactive_session(sc, [_track_dict()], [], "t", None)
        assert b"out of range" in out.getvalue()

    def test_play_action(self):
        runner = CliRunner()
        sc = MagicMock()
        with runner.isolation(input="1\np\nq\n"):
            with patch("nuvem_de_som.cli._resolve_and_play") as rp:
                _interactive_session(sc, [_track_dict()], [], "t", None)
        rp.assert_called_once()

    def test_download_action_success(self):
        runner = CliRunner()
        sc = MagicMock()
        sc.download_track.return_value = Path("/tmp/x.mp3")
        with runner.isolation(input="1\nd\n.\nq\n") as (out, _e, _x):
            _interactive_session(sc, [_track_dict()], [], "t", None)
        assert b"Saved" in out.getvalue()

    def test_download_action_returns_none(self):
        runner = CliRunner()
        sc = MagicMock()
        sc.download_track.return_value = None
        with runner.isolation(input="1\nd\n.\nq\n") as (out, err, _x):
            _interactive_session(sc, [_track_dict()], [], "t", None)
        assert b"Failed to save" in err.getvalue()

    def test_download_action_exception(self):
        runner = CliRunner()
        sc = MagicMock()
        sc.download_track.side_effect = RuntimeError("boom")
        with runner.isolation(input="1\nd\n.\nq\n") as (out, err, _x):
            _interactive_session(sc, [_track_dict()], [], "t", None)
        assert b"Download failed" in err.getvalue()


# ---------------------------------------------------------------------------
# Top-level commands — backends stubbed
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_sc():
    sc = MagicMock()
    sc.search_tracks.return_value = iter([])
    sc.search_people.return_value = iter([])
    sc.search_sets.return_value = iter([])
    sc.get_tracks.return_value = iter([])
    return sc


def _run(stub_sc, args, input=None):
    runner = CliRunner()
    with patch.dict(BACKENDS, {"auto": lambda: stub_sc}):
        return runner.invoke(cli, args, input=input)


class TestSearchCommand:
    def test_search_tracks_no_results(self, stub_sc):
        result = _run(stub_sc, ["search", "foo"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_people(self, stub_sc):
        stub_sc.search_people.return_value = iter([
            Entity(name="P", kind=EntityKind.PERSON,
                   extra={"artist_url": "https://soundcloud.com/p"}),
        ])
        # CLI's _print_people accesses .get on entries — feed dicts via patch.
        with patch("nuvem_de_som.cli._print_people") as pp:
            result = _run(stub_sc, ["search", "--people", "foo"])
        assert result.exit_code == 0
        pp.assert_called_once()

    def test_search_sets_empty(self, stub_sc):
        result = _run(stub_sc, ["search", "--sets", "foo"])
        assert "No sets found" in result.output

    def test_search_sets_with_dict_results(self, stub_sc):
        # The sets branch indexes s['title']/s['url'] directly — feed dicts.
        stub_sc.search_sets.return_value = iter([_set_dict(title="MySet")])
        result = _run(stub_sc, ["search", "--sets", "foo"])
        assert result.exit_code == 0
        assert "MySet" in result.output


class TestBrowseCommand:
    def test_browse_no_results(self, stub_sc):
        result = _run(stub_sc, ["browse", "https://soundcloud.com/u"])
        assert result.exit_code == 0
        assert "No results" in result.output


class TestPlayCommand:
    def test_play_invokes_resolve_and_play(self, stub_sc):
        with patch("nuvem_de_som.cli._resolve_and_play") as rp:
            result = _run(stub_sc, ["play", "https://soundcloud.com/u/t"])
        assert result.exit_code == 0
        rp.assert_called_once()


class TestDownloadCommand:
    def test_download_track_success(self, stub_sc):
        stub_sc.download_track.return_value = Path("/tmp/x.mp3")
        result = _run(stub_sc, ["download", "https://soundcloud.com/u/t"])
        assert result.exit_code == 0
        assert "Saved" in result.output

    def test_download_track_failure(self, stub_sc):
        stub_sc.download_track.return_value = None
        result = _run(stub_sc, ["download", "https://soundcloud.com/u/t"])
        assert result.exit_code == 1
        assert "Download failed" in result.output

    def test_download_playlist_success(self, stub_sc):
        stub_sc.download_playlist.return_value = [Path("/tmp/x.mp3")]
        result = _run(stub_sc, ["download", "--playlist",
                                "https://soundcloud.com/u"])
        assert result.exit_code == 0

    def test_download_playlist_failure(self, stub_sc):
        stub_sc.download_playlist.side_effect = RuntimeError("nope")
        result = _run(stub_sc, ["download", "--playlist",
                                "https://soundcloud.com/u"])
        assert result.exit_code == 1


class TestMain:
    def test_main_runs(self, stub_sc):
        with patch.dict(BACKENDS, {"auto": lambda: stub_sc}):
            with patch("sys.argv", ["nds", "search", "foo"]):
                with pytest.raises(SystemExit):
                    main()

    def test_main_without_click(self):
        with patch.object(cli_module, "click", None):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1


class TestBackendSelection:
    def test_each_backend_choice(self):
        runner = CliRunner()
        for name in BACKENDS:
            stub = MagicMock()
            stub.search_tracks.return_value = iter([])
            with patch.dict(BACKENDS, {name: lambda s=stub: s}):
                result = runner.invoke(cli, ["-b", name, "search", "foo"])
            assert result.exit_code == 0
