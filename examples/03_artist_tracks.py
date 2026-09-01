"""03 — get all tracks for an artist profile using get_tracks().

get_tracks() accepts:
  - artist profile URL  → paginates /users/{id}/tracks
  - set/playlist URL    → reads playlist tracks inline
"""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

artist_url = "https://soundcloud.com/acidkid"
print(f"Tracks for {artist_url}:\n")

total = 0
for release in sc.get_tracks(artist_url, limit=20):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    runtime = int(release.work.runtime) if release.work.runtime else 0
    mins, secs = divmod(runtime, 60)
    genres = ", ".join(release.work.content_genres[:3])
    print(f"  {release.work.title}  [{artist}]  {mins}:{secs:02d}"
          + (f"  ({genres})" if genres else ""))
    total += 1

print(f"\n{total} tracks loaded.")
