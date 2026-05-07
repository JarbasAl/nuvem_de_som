"""Search a SoundCloud set/playlist and emit a typed mediavocab Release.

Demonstrates the enriched output: ``Work.tracklist`` populated with
``Appearance`` entries, plus per-track ``content_genres``, ``license``
(SPDX-mapped) and ``release_date`` whenever SoundCloud exposes them.

Usage::

    python set_tracklist.py "beathop"
    python set_tracklist.py "chillhop"   # any query that returns a set
"""
import sys

from nuvem_de_som import SoundCloudAPI

query = sys.argv[1] if len(sys.argv) > 1 else "chillhop"

sc = SoundCloudAPI()
sets = list(sc.search_sets(query, limit=3))
if not sets:
    print(f"No sets found for {query!r}")
    raise SystemExit(0)

for rel in sets:
    print(f"Set: {rel.work.title}")
    print(f"  uri:           {rel.uri}")
    print(f"  permalink aka: {rel.work.aka}")
    print(f"  license:       {rel.license or '(unset)'}")
    print(f"  release_date:  {rel.release_date or '(unset)'}")
    print(f"  genres:        {rel.work.content_genres}")
    print(f"  tracklist ({len(rel.work.tracklist)} tracks):")
    for app in rel.work.tracklist[:10]:
        artist = ""
        if app.work.credits:
            artist = app.work.credits[0].entity.name
        runtime = (f" [{int(app.work.runtime // 60)}:{int(app.work.runtime % 60):02d}]"
                   if app.work.runtime else "")
        lic = ""
        # The Appearance only carries the Work; per-track Release fields
        # (license, codec, bitrate) live on the parent search/get_tracks result.
        print(f"    {app.position:3}. {app.work.title} — {artist}{runtime}{lic}")
        if app.work.content_genres:
            print(f"          genres: {app.work.content_genres}")
    print()
