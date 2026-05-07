"""07 — mediavocab Release shape from a SoundCloud track.

All search/resolve methods return mediavocab objects directly.
This example inspects every populated field on a single Release.
"""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()

track_url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"
release = sc.resolve_track(track_url)

if not release:
    print("Track not found.")
    raise SystemExit(1)

print("Release fields:")
print(f"  uri:            {release.uri}")
print(f"  image:          {release.image[:60]}..." if release.image else "  image:          (none)")
print(f"  stream_mode:    {release.stream_mode}")
print(f"  codec:          {release.codec}")
print(f"  bitrate:        {release.bitrate} kbps")
print(f"  audio_channels: {release.audio_channels}")
print(f"  license:        {release.license}")
print(f"  release_date:   {release.release_date}")
print(f"  external_ids:   {release.external_ids}")

print()
print("Work fields:")
print(f"  title:          {release.work.title}")
print(f"  media_type:     {release.work.media_type}")
print(f"  runtime:        {release.work.runtime}s")
print(f"  content_genres: {release.work.content_genres}")
print(f"  country:        {release.work.country}")
print(f"  aka:            {release.work.aka}")
print(f"  external_ids:   {release.work.external_ids}")

if release.work.credits:
    c = release.work.credits[0]
    print()
    print("Credit[0]:")
    print(f"  entity.name:         {c.entity.name}")
    print(f"  entity.kind:         {c.entity.kind}")
    print(f"  entity.external_ids: {c.entity.external_ids}")
    print(f"  role:                {c.role}")
    print(f"  relation_role:       {c.relation_role}")
    print(f"  section:             {c.section}")
