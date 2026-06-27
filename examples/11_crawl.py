"""11 — discover artists via social-graph BFS (SoundCloudAPI.crawl).

Seeds can be profile URLs or keyword query strings.
"""
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI()
seen = set()
for entity in sc.crawl(
    ["https://soundcloud.com/noisia", "black metal"],
    social_depth=20,
    max_artists=10,
    seen=seen,
):
    print(
        entity.name,
        entity.extra.get("followers_count", "?"),
        "verified" if entity.extra.get("verified") else "",
    )
