"""02 — search artists and playlists/sets."""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

query = "acidkid"

print(f"Artists matching {query!r}:")
for entity in sc.search_people(query, limit=5):
    print(f"  {entity.name}  <{entity.extra.get('artist_url', '')}>")
    if entity.extra.get("country"):
        print(f"    country: {entity.extra['country']}")

print()
print(f"Sets matching {query!r}:")
for release in sc.search_sets(query, limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    track_count = len(release.work.tracklist)
    print(f"  {release.work.title}  [{artist}]  {track_count} tracks  →  {release.uri}")
