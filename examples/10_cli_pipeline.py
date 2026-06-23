"""10 — nds CLI pipeline in Python (shell workflow equivalent).

Equivalent shell commands are shown as comments.
Requires: pip install "nuvem_de_som[cli]"
"""
from nuvem_de_som import SoundCloudAPI

# nds search "nuclear chill" --limit 5
# (non-interactive, prints results but won't prompt in a pipeline)
print("=== nds search (non-interactive) ===")
print("$ nds --backend api search 'ambient' --limit 5")
# Use SoundCloudAPI directly for scriptable output
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
