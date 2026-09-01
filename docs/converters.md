# mediavocab converters

All public methods return `mediavocab` objects directly. No explicit
conversion step is needed.

## Release (tracks and sets)

`_track_dict_to_release`: `nuvem_de_som/__init__.py:250`
`_set_dict_to_release`: `nuvem_de_som/__init__.py:357`

`search_tracks`, `get_tracks`, `resolve_track`, and `search_sets` return this type.

| Field | Type | Source |
|---|---|---|
| `release.uri` | `str` | SoundCloud `permalink_url` |
| `release.image` | `str` | `artwork_url` or uploader `avatar_url`, or `""` when absent |
| `release.stream_mode` | `StreamMode` | Always `StreamMode.ON_DEMAND` |
| `release.codec` | `str` | Best transcoding `mime_type` (for example `"audio/mpeg"`) |
| `release.bitrate` | `str` | `"256"` (hq) or `"128"` (sq) from transcoding quality |
| `release.audio_channels` | `str` | `"stereo"` when the codec is known, else `""` |
| `release.license` | `str` | SPDX id (see table below) or the raw SoundCloud value |
| `release.release_date` | `str \| None` | ISO date from `display_date` or `created_at` |
| `release.external_ids["soundcloud_track_id"]` | `str` | SoundCloud track numeric id |
| `release.external_ids["soundcloud_user_id"]` | `str` | SoundCloud uploader numeric id |
| `release.work.title` | `str` | Track title |
| `release.work.media_type` | `MediaType` | Always `MediaType.MUSIC` |
| `release.work.runtime` | `float \| None` | `duration / 1000` seconds |
| `release.work.credits[0].entity.name` | `str` | Uploader `username` |
| `release.work.credits[0].relation_role` | `RelationRole` | `PERFORMER` (tracks) or `CREATOR` (sets) |
| `release.work.extra["artist_url"]` | `str` | Uploader `permalink_url` |
| `release.work.aka` | `list[str]` | `[permalink]` (URL slug) |
| `release.work.content_genres` | `list[str]` | From `genre` and `tag_list`, mapped to `GENRE_*` constants when recognized |
| `release.work.production_country` | `str` | Uploader `country_code` (ISO 3166 alpha-2) |
| `release.work.external_ids` | `dict` | Same ids as `release.external_ids` |

For sets, `release.work.tracklist` is a `list[Appearance]` with positions
1..N. `release.external_ids["soundcloud_playlist_id"]` is also populated.

Fields marked "SoundCloudAPI only" are empty (`""`, `None`, `[]`) when the
HTML backend is used, because SoundCloud's search and track HTML does not
expose them.

## Entity (artists / users)

`_user_dict_to_entity`: `nuvem_de_som/__init__.py:326`

`search_people` and `resolve_user` return this type.

| Field | Type | Source |
|---|---|---|
| `entity.name` | `str` | `username` |
| `entity.kind` | `EntityKind` | Always `EntityKind.PERSON` |
| `entity.external_ids["soundcloud_user_id"]` | `str` | SoundCloud user numeric id |
| `entity.extra["artist_url"]` | `str` | Profile `permalink_url` |
| `entity.extra["image"]` | `str` | `avatar_url` |
| `entity.extra["country"]` | `str` | `country_code` (when present) |
| `entity.extra["permalink"]` | `str` | URL slug (when present) |

## License mapping

`_map_license`: `nuvem_de_som/__init__.py:98`

| SoundCloud value | SPDX id |
|---|---|
| `no-rights-reserved` | `CC0-1.0` |
| `cc-by` | `CC-BY-4.0` |
| `cc-by-nc` | `CC-BY-NC-4.0` |
| `cc-by-nd` | `CC-BY-ND-4.0` |
| `cc-by-sa` | `CC-BY-SA-4.0` |
| `cc-by-nc-nd` | `CC-BY-NC-ND-4.0` |
| `cc-by-nc-sa` | `CC-BY-NC-SA-4.0` |
| `all-rights-reserved` | `"all-rights-reserved"` (passed through) |

## Genre mapping

`_build_genres`: `nuvem_de_som/__init__.py:105`

This combines the SoundCloud `genre` field and `tag_list` (space-separated,
quoted for multi-word tags). Each token is looked up against
`mediavocab.taxonomy.genre.GENRE_*` constants, trying the token itself, its
underscore-normalized form, and the `&`-to-`and` variant. Unrecognized
tokens are kept as-is. Duplicates are discarded.

---
[← Streams and transcodings](streams.md) · [Home](../README.md) · [Transport →](transport.md)
