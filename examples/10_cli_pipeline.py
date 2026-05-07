"""10 — nds CLI pipeline in Python (shell workflow equivalent).

Equivalent shell commands are shown as comments.
Requires: pip install "nuvem_de_som[cli]"
"""
import subprocess
import sys


def run(args):
    """Run nds with args, print output, return stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "nuvem_de_som.cli"] + args,
        capture_output=True, text=True,
    )
    # Also try the nds entry point if installed
    if result.returncode != 0:
        result = subprocess.run(
            ["nds"] + args,
            capture_output=True, text=True,
        )
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.stdout


# nds search "nuclear chill" --limit 5
# (non-interactive, prints results but won't prompt in a pipeline)
print("=== nds search (non-interactive) ===")
print("$ nds --backend api search 'ambient' --limit 5")
# Use SoundCloudAPI directly for scriptable output
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()
for release in sc.search_tracks("ambient", limit=5):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  {release.work.title}  [{artist}]  →  {release.uri}")

print()
print("=== nds browse (list tracks for artist) ===")
print("$ nds browse https://soundcloud.com/acidkid --limit 10")
for release in sc.get_tracks("https://soundcloud.com/acidkid", limit=10):
    print(f"  {release.work.title}  →  {release.uri}")

print()
print("=== resolve stream URL ===")
url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"
stream = sc.resolve_stream(url)
if stream:
    print(f"  {stream[:100]}...")
    print()
    print("  Play with: mpv --no-video '<stream_url>'")
    print("  Or: nds play", url)
