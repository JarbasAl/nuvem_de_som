"""Search SoundCloud tracks (no stream extraction — just URLs)."""
import sys
from nuvem_de_som import SoundCloud

query = sys.argv[1] if len(sys.argv) > 1 else "ambient"

sc = SoundCloud()
print(f"Tracks for: {query!r}\n")
for release in sc.search_tracks(query, limit=10):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  {release.work.title}  ({artist})  →  {release.uri}")
