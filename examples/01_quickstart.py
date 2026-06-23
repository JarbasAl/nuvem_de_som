"""01 — search and resolve one track.

Uses the SoundCloud orchestrator (API → yt-dlp → HTML fallback).
"""
from nuvem_de_som import SoundCloud

sc = SoundCloud()

query = "nuclear chill"
print(f"Searching: {query!r}\n")

results = list(sc.search_tracks(query, limit=5))
for release in results:
    artist = release.work.credits[0].entity.name if release.work.credits else "(unknown)"
    runtime = int(release.work.runtime) if release.work.runtime else 0
    mins, secs = divmod(runtime, 60)
    print(f"  {release.work.title}  [{artist}]  {mins}:{secs:02d}  →  {release.uri}")

if results:
    first = results[0]
    print(f"\nResolving stream for: {first.uri}")
    stream = sc.resolve_stream(first.uri)
    if stream:
        print(f"  Stream URL: {stream[:80]}...")
    else:
        print("  Could not resolve stream URL.")
