"""08 — inject a custom HTTP session.

Use curl_cffi for browser-impersonating transport when SoundCloud blocks
standard requests. Requires: pip install nuvem_de_som[stealth]

Alternatively, set NUVEM_TRANSPORT=curl_cffi and let default_session() pick
the right backend automatically.
"""
import os
from nuvem_de_som import SoundCloudAPI, SoundCloudHTML, SoundCloud

# --- Option A: env var (applies to default_session() in all backends) --------
# os.environ["NUVEM_TRANSPORT"] = "curl_cffi"
# sc = SoundCloud()   # will use curl_cffi if installed

# --- Option B: inject directly -----------------------------------------------
try:
    from curl_cffi import requests as cffi_requests

    session = cffi_requests.Session(impersonate="chrome120")
    print("Using curl_cffi session (chrome120 impersonation)")
except ImportError:
    import requests
    session = requests.Session()
    print("curl_cffi not installed; using plain requests.Session()")
    print("  Install with: pip install 'nuvem_de_som[stealth]'")

# Same session shared by API and HTML backends
sc_api = SoundCloudAPI(session=session)
sc_html = SoundCloudHTML(session=session)
sc_orch = SoundCloud(session=session)   # forwarded to API + HTML; yt-dlp ignores it

print()
print("Search via SoundCloudAPI with custom session:")
for release in sc_api.search_tracks("ambient", limit=3):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  {release.work.title}  [{artist}]")
