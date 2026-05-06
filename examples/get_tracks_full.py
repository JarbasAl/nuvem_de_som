"""List all tracks on a SoundCloud artist or set page.

Paginates through the full catalogue via SoundCloud's internal API
instead of being limited to the ~20 items visible in the initial HTML page.

Usage:
    python get_tracks_full.py https://soundcloud.com/acidkid
    python get_tracks_full.py https://soundcloud.com/acidkid/sets/acid 50
"""
import sys
from nuvem_de_som import SoundCloud

url = sys.argv[1] if len(sys.argv) > 1 else "https://soundcloud.com/acidkid"
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 200

sc = SoundCloud()
print(f"Fetching tracks for: {url}  (limit={limit})\n")
for i, release in enumerate(sc.get_tracks(url, limit=limit), 1):
    rt = release.work.runtime
    duration = f"  [{int(rt // 60)}:{int(rt % 60):02d}]" if rt is not None else ""
    print(f"{i:3}. {release.work.title}{duration}")
    print(f"     {release.uri}")
