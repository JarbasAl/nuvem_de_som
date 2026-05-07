"""Unit tests for the pure-function transcoding picker.

These don't hit the network — they pin the recent fix where the
progressive transcoding must win over HLS so codec/bitrate describe
a directly-playable stream rather than an m3u8 variant.
"""
from __future__ import annotations

from nuvem_de_som import _parse_transcodings


def _entry(protocol: str, mime: str, quality: str) -> dict:
    return {
        "format": {"protocol": protocol, "mime_type": mime},
        "quality": quality,
    }


def test_progressive_preferred_over_hls_when_both_present():
    transcodings = [
        _entry("hls", "audio/ogg", "hq"),
        _entry("progressive", "audio/mpeg", "sq"),
    ]
    codec, bitrate = _parse_transcodings(transcodings)
    # progressive entry wins even though hls is "hq" — the fix.
    assert codec == "audio/mpeg"
    assert bitrate == "128"


def test_hq_preferred_within_progressive_pool():
    transcodings = [
        _entry("progressive", "audio/mpeg", "sq"),
        _entry("progressive", "audio/mpeg", "hq"),
    ]
    codec, bitrate = _parse_transcodings(transcodings)
    assert codec == "audio/mpeg"
    assert bitrate == "256"


def test_falls_back_to_hls_when_no_progressive():
    transcodings = [_entry("hls", "audio/ogg", "hq")]
    codec, bitrate = _parse_transcodings(transcodings)
    assert codec == "audio/ogg"
    assert bitrate == "256"


def test_empty_returns_empty_strings():
    assert _parse_transcodings([]) == ("", "")
