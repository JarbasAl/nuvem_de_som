# nuvem_de_som API

See the split docs for full coverage:

- [Getting started](getting-started.md)
- [Backends reference](backends.md) — `SoundCloudAPI`, `SoundCloudHTML`, `SoundCloudYTDLP`, `SoundCloud`
- [Streams and transcodings](streams.md) — `resolve_stream`, progressive vs HLS, `_parse_transcodings`
- [mediavocab converters](converters.md) — `Release` and `Entity` field reference
- [Transport](transport.md) — `default_session`, `NUVEM_TRANSPORT`, curl_cffi
- [CLI reference](cli.md) — `nds` commands and options

---

## SoundCloudAPI — additional methods

### `get_followers(profile_url, limit=200)`

Yields `Entity` objects for users who follow the given profile.

```python
sc = SoundCloudAPI()
for follower in sc.get_followers("https://soundcloud.com/noisia", limit=50):
    print(follower.name, follower.extra.get("followers_count"))
```

Resolves the profile URL to a numeric user id first, then paginates
`/users/{id}/followers` with `linked_partitioning=1`.  Returns immediately
if the profile URL cannot be resolved.

Parameters:

| Name | Type | Default | Description |
|---|---|---|---|
| `profile_url` | `str` | — | SoundCloud profile URL |
| `limit` | `int` | `200` | Maximum number of followers to yield |

Returns: `Iterator[mediavocab.Entity]`

---

### `get_following(profile_url, limit=200)`

Yields `Entity` objects for users that the given profile follows.

```python
for followed in sc.get_following("https://soundcloud.com/noisia", limit=50):
    print(followed.name)
```

Same pagination behaviour as `get_followers`; paginates `/users/{id}/followings`.

Returns: `Iterator[mediavocab.Entity]`

---

### `get_reposts(profile_url, limit=50)`

Yields `Release` objects for tracks reposted by the given profile.

```python
for release in sc.get_reposts("https://soundcloud.com/noisia", limit=20):
    print(release.work.title, release.uri)
```

Paginates `/stream/users/{id}/reposts`.  Items without a title are silently
skipped.

Returns: `Iterator[mediavocab.Release]`

---

### `crawl(seeds, *, social_depth=50, max_artists=0, seen=None)`

BFS generator that discovers artists via their social graph.

```python
seen = set()
for entity in sc.crawl(
    ["https://soundcloud.com/noisia", "black metal"],
    social_depth=20,
    max_artists=100,
    seen=seen,
):
    print(entity.name, entity.extra.get("followers_count"))
```

Seeds may be SoundCloud profile URLs **or** keyword query strings.  A
keyword seed is resolved to the top `search_people` result; if resolution
fails it is skipped.  For each artist in the frontier, up to `social_depth`
followers and followings are fetched and enqueued.

Parameters:

| Name | Type | Default | Description |
|---|---|---|---|
| `seeds` | `list[str]` | — | Profile URLs or keyword query strings |
| `social_depth` | `int` | `50` | Max followers/followings to enqueue per artist |
| `max_artists` | `int` | `0` | Stop after this many yields (0 = unlimited) |
| `seen` | `set[str] \| None` | `None` | Mutable set of visited URLs — mutated in-place for resumability |

Returns: `Iterator[mediavocab.Entity]`

The `seen` set is mutated in-place.  Pass the same set across multiple
`crawl()` calls to resume without revisiting already-seen profiles.

---

## Entity — extra fields

All people methods (`search_people`, `resolve_user`, `get_followers`,
`get_following`) populate the following fields via `_sc_user_to_dict()`:

| `entity.extra` key | Source | Notes |
|---|---|---|
| `"artist_url"` | `permalink_url` | Full profile URL |
| `"image"` | `avatar_url` | Avatar image URL |
| `"country"` | `country_code` | ISO 3166 alpha-2 when known |
| `"permalink"` | `permalink` | URL slug |
| `"verified"` | `verified` | `"1"` when the account is verified; key absent otherwise |
| `"followers_count"` | `followers_count` | String int when present in the API response |
| `"followings_count"` | `followings_count` | String int when present in the API response |
| `"track_count"` | `track_count` | String int when present in the API response |

All count fields are stored as strings (the `Entity.extra` dict is
`dict[str, str]`).  Convert as needed:

```python
followers = int(entity.extra.get("followers_count") or 0)
verified   = bool(entity.extra.get("verified"))
```
