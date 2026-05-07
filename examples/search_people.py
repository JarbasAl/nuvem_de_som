"""Search SoundCloud for artists and list their top tracks."""
import sys
from nuvem_de_som import SoundCloud

query = sys.argv[1] if len(sys.argv) > 1 else "acidkid"

sc = SoundCloud()
print(f"Artists for: {query!r}\n")
for entity in sc.search_people(query, limit=5):
    artist_url = entity.extra.get("artist_url", "")
    print(f"Artist: {entity.name}  {artist_url}")
    if artist_url:
        for release in list(sc.get_tracks(artist_url, limit=5)):
            print(f"  - {release.work.title}  {release.uri}")
    print()
