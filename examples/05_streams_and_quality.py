"""05 — inspect transcodings and resolve stream URLs.

SoundCloudAPI.resolve_stream() picks the best progressive transcoding and
returns a direct audio URL — no yt-dlp required.
"""
from nuvem_de_som import SoundCloudAPI
from nuvem_de_som import _get_client_id

sc = SoundCloudAPI()

track_url = "https://soundcloud.com/acidkid/piratech-nuclear-chill"

# Fetch raw transcodings from the API
cid = _get_client_id(session=sc.session)
resp = sc.session.get(
    "https://api-v2.soundcloud.com/resolve",
    params={"url": track_url, "client_id": cid},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()

transcodings = (data.get("media") or {}).get("transcodings") or []
print(f"Transcodings for: {data.get('title')}\n")
for t in transcodings:
    fmt = t.get("format") or {}
    print(f"  protocol={fmt.get('protocol'):15s}  mime={fmt.get('mime_type'):15s}"
          f"  quality={t.get('quality')}")

print()
print("resolve_stream(prefer='progressive'):")
url = sc.resolve_stream(track_url, prefer="progressive")
if url:
    print(f"  {url[:80]}...")
else:
    print("  None")

print()
print("resolve_stream(prefer='hls'):")
url = sc.resolve_stream(track_url, prefer="hls")
if url:
    print(f"  {url[:80]}...")
else:
    print("  None")
