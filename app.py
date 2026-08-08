"""
ICP Capture Kit server v3.

  GET  /              -> the page
  GET  /kestrel       -> public sample run (static, no model or Apollo calls)
  POST /api/analyze   -> {domain, force} -> {slug, assets, market{prospects...}}
                         Fast half: scrape + assets + prospects, no sequences.
                         Once-per-domain: if a stored kit exists, returns its share_url.
  POST /api/sequence  -> {assets, prospect} -> one prospect's kit {prospect, about, emails}
                         The front-end calls this once per prospect, in parallel.
  POST /api/share     -> {kit} -> renders + stores the share page, returns {share_url}
  POST /api/capture   -> {domain, force} -> whole kit in one call (CLI/back-compat only;
                         may exceed a 60s serverless cap, which is why the UI uses the split).
  GET  /k/{slug}      -> redirects to the stored share page for a domain

The API is split into analyze + per-prospect sequence + share so that NO single
request runs all five Claude sequence calls, which pushed the combined run past
Vercel's 60s function cap.

Env: ANTHROPIC_API_KEY, APOLLO_API_KEY, APOLLO_ENRICH=1,
     BLOB_READ_WRITE_TOKEN (auto-added when you enable Blob storage on Vercel).
"""
import re, pathlib
from typing import Any, Dict, List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import capture, storage, report_html

HERE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="ICP Capture Kit")

def _slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9]", "", domain.strip().lower()
                  .replace("https://", "").replace("http://", "")
                  .replace("www.", "").split("/")[0].split(".")[0])

class DomainReq(BaseModel):
    domain: str
    force: bool = False    # pass force:true to regenerate past the once-per-domain cache

class SequenceReq(BaseModel):
    assets: Dict[str, Any] = {}
    prospect: Dict[str, Any] = {}

class ShareReq(BaseModel):
    slug: str
    domain: str = ""
    assets: Dict[str, Any] = {}
    market: Dict[str, Any] = {}
    prospect_kits: List[Dict[str, Any]] = []
    total_emails: int = 0

@app.get("/", response_class=HTMLResponse)
def home():
    html = (HERE / "web" / "index.html").read_text(encoding="utf-8")
    # no-store so a new deploy's UI is served immediately instead of a stale copy.
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})

@app.get("/kestrel", response_class=HTMLResponse)
def sample():
    """Public sample run, safe to link anywhere (LinkedIn featured, email, deck).

    Fully static: no scrape, no Claude call, no Apollo call, so linking it
    publicly cannot burn credits. Kestrel is a made-up company and the prospects
    on the page are invented; the page says so at the top."""
    html = (HERE / "web" / "kestrel.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})

@app.post("/api/analyze")
def analyze(req: DomainReq):
    slug = _slug(req.domain)
    # once-per-domain limit: serve the stored kit if it exists. share_url is the
    # /k/<slug> path on our domain (renders inline), not the raw blob URL.
    if not req.force:
        if storage.find_kit(slug):
            return JSONResponse({"cached": True, "share_url": "/k/" + slug, "slug": slug})
    try:
        base = capture.analyze(req.domain)
        base["cached"] = False
        return JSONResponse(base)
    except capture.SiteUnreadable as e:
        # Not our bug: the site gave us no brief. 422 (not 500) and the reason
        # verbatim, so the UI tells the visitor what happened.
        return JSONResponse({"error": str(e)}, status_code=422)
    except (Exception, SystemExit) as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.post("/api/sequence")
def sequence(req: SequenceReq):
    try:
        # sequence_for captures per-prospect failures on the kit itself, so this
        # returns a usable {prospect, about, emails, error?} even when the model call fails.
        return JSONResponse(capture.sequence_for(req.assets, req.prospect))
    except (Exception, SystemExit) as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.post("/api/share")
def share_page(req: ShareReq):
    kit = req.model_dump()
    try:
        # Never store a kit built on an empty brief: the stored page IS the
        # once-per-domain cache, so caching garbage keeps serving it forever
        # (that is how the empty fresco-ai.com kit became the live page).
        if not capture.has_brief(kit.get("assets")):
            return JSONResponse({"share_url": None, "slug": kit["slug"],
                                 "share_error": "not stored: this kit has no company name or "
                                 "product summary, so the site was never really read"},
                                status_code=422)
        if not any(pk.get("emails") for pk in kit.get("prospect_kits") or []):
            return JSONResponse({"share_url": None, "slug": kit["slug"],
                                 "share_error": "not stored: the kit contains no emails"},
                                status_code=422)
        if not storage.enabled():
            return JSONResponse({"share_url": None, "slug": kit["slug"],
                                 "share_error": "blob storage not enabled "
                                 "(BLOB_READ_WRITE_TOKEN missing at runtime)"})
        share = storage.save_kit(kit["slug"], report_html.render(kit))
        # Return the /k/<slug> path on our domain (renders inline) rather than
        # the raw blob URL (which downloads as an attachment).
        out = {"share_url": ("/k/" + kit["slug"]) if share else None, "slug": kit["slug"]}
        if not share:
            out["share_error"] = storage.last_error()
        return JSONResponse(out)
    except (Exception, SystemExit) as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.post("/api/capture")
def make(req: DomainReq):
    """Whole kit in one request. CLI/back-compat only; the UI uses the split API
    because running all five sequences here can exceed the 60s cap."""
    slug = _slug(req.domain)
    if not req.force:
        if storage.find_kit(slug):
            return JSONResponse({"cached": True, "share_url": "/k/" + slug, "slug": slug})
    try:
        kit = capture.build_kit(req.domain)
        share = None
        if storage.enabled():
            share = storage.save_kit(kit["slug"], report_html.render(kit))
        kit["share_url"] = ("/k/" + kit["slug"]) if share else None
        if not share:
            kit["share_error"] = (storage.last_error() if storage.enabled()
                                  else "blob storage not enabled (BLOB_READ_WRITE_TOKEN missing at runtime)")
        kit["cached"] = False
        return JSONResponse(kit)
    except capture.SiteUnreadable as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except (Exception, SystemExit) as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.get("/k/{slug}")
def share(slug: str):
    # Serve the stored page inline from our own domain. We fetch the blob server
    # side and return it as text/html; redirecting to the raw blob URL would make
    # the browser DOWNLOAD the file (Vercel Blob sets content-disposition:attachment).
    html = storage.fetch_kit_html(re.sub(r"[^a-z0-9]", "", slug.lower()))
    if html:
        # Count the visit even for kits stored before the analytics snippet existed:
        # inject it on the way out (idempotent) rather than rewriting every blob.
        # Pages rendered from now on already carry it, from report_html.
        if "/_vercel/insights/script.js" not in html:
            html = html.replace("</head>", report_html.ANALYTICS + "</head>", 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"error": "no kit found for that domain"}, status_code=404)
