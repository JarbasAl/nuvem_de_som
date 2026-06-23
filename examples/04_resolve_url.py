"""04 — resolve a track or user URL to a mediavocab object."""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

track_url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"
user_url = "https://soundcloud.com/acidkid"

print("resolve_track():")
release = sc.resolve_track(track_url)
if release:
    artist = release.work.credits[0].entity.name if release.work.credits else "(unknown)"
    print(f"  title:        {release.work.title}")
    print(f"  artist:       {artist}")
    print(f"  runtime:      {release.work.runtime}s")
    print(f"  genres:       {release.work.content_genres}")
    print(f"  license:      {release.license}")
    print(f"  release_date: {release.release_date}")
    print(f"  codec:        {release.codec}")
    print(f"  bitrate:      {release.bitrate} kbps")
    print(f"  external_ids: {release.external_ids}")
else:
    print("  Not found.")

print()
print("resolve_user():")
entity = sc.resolve_user(user_url)
if entity:
    print(f"  name:         {entity.name}")
    print(f"  artist_url:   {entity.extra.get('artist_url')}")
    print(f"  country:      {entity.extra.get('country', '(unknown)')}")
    print(f"  external_ids: {entity.external_ids}")
else:
    print("  Not found.")
