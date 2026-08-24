"""
Vercel Blob storage for shareable kit pages + offer reviews + once-per-domain limiting.

Setup (one time, in Vercel dashboard):
  Project -> Storage -> Create -> Blob. Vercel auto-adds BLOB_READ_WRITE_TOKEN
  to the project env. Redeploy. Done.

Every generated kit is stored as kits/kit-<slug>.html at a public URL. That URL is
the shareable link AND the cache: if a kit already exists for a domain, we serve the
stored one instead of re-running (the once-per-domain limit, durable).

Offer reviews are stored as reviews/<slug>.json (public). The recipient-facing page
at fareehafatima.co/review?c=<slug> tries local static files first, then falls back
to the Blob URL, so portal-generated reviews are live instantly with no redeploy.

Errors are captured (not swallowed) in last_error() so the API can report exactly
why a share link could not be produced.
"""
import os, json, urllib.request, urllib.error

API = "https://blob.vercel-storage.com"

_LAST_ERROR = None

def _token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", "")

def enabled():
    return bool(_token())

def last_error():
    return _LAST_ERROR

def _req(url, method="GET", data=None, headers=None):
    h = {"authorization": "Bearer " + _token(), "x-api-version": "7"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "ignore") or "{}")

def _capture(where, exc):
    """Record a readable reason for a Blob failure and return None."""
    global _LAST_ERROR
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        _LAST_ERROR = f"{where}: HTTP {exc.code} {exc.reason} {body[:400]}".strip()
    else:
        _LAST_ERROR = f"{where}: {type(exc).__name__}: {exc}"
    return None

def find_kit(slug):
    """Return the public URL of an existing kit page for this slug, else None."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return None
    try:
        r = _req(f"{API}?prefix=kits/kit-{slug}.html&limit=1")
        blobs = r.get("blobs") or []
        return blobs[0]["url"] if blobs else None
    except Exception as e:
        return _capture("find_kit", e)

def fetch_kit_html(slug):
    """Download the stored share page's HTML for a slug, or None. Used to serve
    the page inline through our own domain (/k/<slug>): the raw Blob URL is sent
    with content-disposition: attachment, so linking to it downloads the file
    instead of rendering it."""
    global _LAST_ERROR
    _LAST_ERROR = None
    url = find_kit(slug)
    if not url:
        return None
    try:
        # public blob: a plain GET needs no auth
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:
        return _capture("fetch_kit_html", e)

def save_kit(slug, html):
    """Upload the share page; returns its public URL (stable path, overwrite allowed)."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return None
    try:
        r = _req(f"{API}/kits/kit-{slug}.html", method="PUT",
                 data=html.encode("utf-8"),
                 headers={"content-type": "text/html; charset=utf-8",
                          "x-content-type": "text/html; charset=utf-8",
                          "x-add-random-suffix": "0",
                          "x-allow-overwrite": "1"})
        url = r.get("url")
        if not url:
            _LAST_ERROR = f"save_kit: no url in Blob response: {json.dumps(r)[:400]}"
        return url
    except Exception as e:
        return _capture("save_kit", e)

# ---------------------------------------------------------------- reviews

def fetch_review(slug):
    """Fetch stored review JSON by slug, or None if not found."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return None
    try:
        r = _req(f"{API}?prefix=reviews/{slug}.json&limit=1")
        blobs = r.get("blobs") or []
        if not blobs:
            return None
        url = blobs[0]["url"]
        # fetch the JSON
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as e:
        return _capture("fetch_review", e)

def save_review(slug, review_data):
    """Upload review JSON to reviews/<slug>.json; returns True on success."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return False
    try:
        payload = json.dumps(review_data, indent=2, ensure_ascii=False).encode("utf-8")
        r = _req(f"{API}/reviews/{slug}.json", method="PUT",
                 data=payload,
                 headers={"content-type": "application/json; charset=utf-8",
                          "x-content-type": "application/json; charset=utf-8",
                          "x-add-random-suffix": "0",
                          "x-allow-overwrite": "1"})
        url = r.get("url")
        if not url:
            _LAST_ERROR = f"save_review: no url in Blob response: {json.dumps(r)[:400]}"
            return False
        return True
    except Exception as e:
        _capture("save_review", e)
        return False

# ---------------------------------------------------------------- kit JSON

def fetch_kit_json(slug):
    """Fetch stored kit JSON by slug, or None if not found."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return None
    try:
        r = _req(f"{API}?prefix=kits/kit-{slug}.json&limit=1")
        blobs = r.get("blobs") or []
        if not blobs:
            return None
        url = blobs[0]["url"]
        # fetch the JSON
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as e:
        return _capture("fetch_kit_json", e)

def save_kit_json(slug, kit_data):
    """Upload kit JSON to kits/kit-<slug>.json; returns True on success."""
    global _LAST_ERROR
    _LAST_ERROR = None
    if not enabled():
        _LAST_ERROR = "BLOB_READ_WRITE_TOKEN not set at runtime"
        return False
    try:
        payload = json.dumps(kit_data, indent=2, ensure_ascii=False).encode("utf-8")
        r = _req(f"{API}/kits/kit-{slug}.json", method="PUT",
                 data=payload,
                 headers={"content-type": "application/json; charset=utf-8",
                          "x-content-type": "application/json; charset=utf-8",
                          "x-add-random-suffix": "0",
                          "x-allow-overwrite": "1"})
        url = r.get("url")
        if not url:
            _LAST_ERROR = f"save_kit_json: no url in Blob response: {json.dumps(r)[:400]}"
            return False
        return True
    except Exception as e:
        _capture("save_kit_json", e)
        return False
