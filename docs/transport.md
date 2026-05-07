# Transport

`nuvem_de_som.transport.default_session` — `nuvem_de_som/transport.py:35`

## How it works

`SoundCloudAPI`, `SoundCloudHTML`, and `SoundCloud` all call `default_session()`
if no `session=` kwarg is provided. `default_session()` checks:

1. If `NUVEM_TRANSPORT=curl_cffi` is set **and** `curl_cffi` is importable →
   returns `curl_cffi.requests.Session(impersonate="chrome")`.
2. Otherwise → returns `requests.Session()`.

If `NUVEM_TRANSPORT=curl_cffi` is set but `curl_cffi` is not installed, a
`WARNING` is logged and the call falls back to `requests.Session()`.

## curl_cffi — browser impersonation

SoundCloud fingerprints TLS (JA3) and HTTP/2 frame ordering. A stock
`requests.Session` may be blocked. `curl_cffi` impersonates a real browser at
the transport layer.

```bash
pip install "nuvem_de_som[stealth]"
export NUVEM_TRANSPORT=curl_cffi
python myscript.py
```

Or inject directly:

```python
from curl_cffi import requests as cffi_requests
from nuvem_de_som import SoundCloudAPI

sc = SoundCloudAPI(session=cffi_requests.Session(impersonate="chrome120"))
```

Any session-like object with `.get(url, ...)` is accepted.

## SoundCloudYTDLP

`SoundCloudYTDLP` does **not** accept a `session=` kwarg and ignores
`NUVEM_TRANSPORT`. yt-dlp manages its own networking stack.

## Environment variable

| Variable | Values | Effect |
|---|---|---|
| `NUVEM_TRANSPORT` | `curl_cffi` | Use curl_cffi session if importable |
| `NUVEM_TRANSPORT` | _(unset)_ | Use requests.Session() |
