"""09 — SoundCloud orchestrator: picking the right backend.

SoundCloud tries API → yt-dlp → HTML in order and returns the first success.
This example demonstrates the fallback chain and shows which backend answered.
"""
import logging
from nuvem_de_som import SoundCloud, SoundCloudAPI, SoundCloudYTDLP, SoundCloudHTML

# Enable debug to see which backends are tried
logging.basicConfig(level=logging.DEBUG,
                    format="%(name)s %(levelname)s %(message)s")

sc = SoundCloud()

# The orchestrator exposes the internal chain:
print("Backend chain:")
for b in sc._chain:
    print(f"  {type(b).__name__}")

print()
print("search_tracks — first backend to return results wins:")
for release in sc.search_tracks("lo-fi beats", limit=3):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  {release.work.title}  [{artist}]")

print()
print("resolve_stream — API first, yt-dlp fallback:")
url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"
stream = sc.resolve_stream(url)
if stream:
    print(f"  {stream[:80]}...")

print()
print("download_track — API first, yt-dlp fallback:")
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    try:
        path = sc.download_track(url, output_dir=tmp)
        if path:
            import os
            size = os.path.getsize(path)
            print(f"  Saved: {path}  ({size // 1024} KB)")
    except Exception as exc:
        print(f"  Failed: {exc}")
