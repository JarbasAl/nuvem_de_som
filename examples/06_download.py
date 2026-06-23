"""06 — download a track with each backend.

SoundCloudAPI.download_track() uses pure requests (no yt-dlp).
SoundCloudYTDLP.download_track() uses yt-dlp (pip install nuvem_de_som[yt-dlp]).
SoundCloud (orchestrator) tries API first, yt-dlp fallback.
"""
import sys
import tempfile
from pathlib import Path

from nuvem_de_som import SoundCloudAPI

track_url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"

with tempfile.TemporaryDirectory() as tmp:
    print(f"Downloading (API backend, pure requests): {track_url}")
    try:
        sc = SoundCloudAPI()
        path = sc.download_track(track_url, output_dir=tmp)
        size = Path(path).stat().st_size
        print(f"  Saved: {path}  ({size // 1024} KB)")
    except Exception as exc:
        print(f"  Failed: {exc}", file=sys.stderr)

# Uncomment to try yt-dlp backend (pip install nuvem_de_som[yt-dlp]):
# from nuvem_de_som import SoundCloudYTDLP
# with tempfile.TemporaryDirectory() as tmp:
#     sc = SoundCloudYTDLP()
#     path = sc.download_track(track_url, output_dir=tmp, verbose=True)
#     print(f"  Saved: {path}")
