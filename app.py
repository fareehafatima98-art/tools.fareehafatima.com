"""
ICP Capture Kit server v3 + Tools Portal.

PUBLIC ROUTES:
  GET  /              -> the page
  GET  /kestrel       -> public sample run (static, no model or Apollo calls)
  POST /api/analyze   -> {domain, force} -> {slug, assets, market{prospects...}}
                         Fast half: scrape + assets + prospects, no sequences.
                         Once-per-domain: if a stored kit exists, returns its share_url.
  POST /api/sequence  -> {assets, prospect} -> one prospect's kit {prospect, about, emails}
                         The front-end calls this once per prospect, in parallel.
  POST /api/share     -> {kit} -> renders + stores the share page AND kit JSON, returns {share_url}
  POST /api/capture   -> {domain, force} -> whole kit in one call (CLI/back-compat only;
                         may exceed a 60s serverless cap, which is why the UI uses the split).
  GET  /k/{slug}      -> serve the stored share page for a domain (inline HTML)
  GET  /api/kit/{slug} -> retrieve the stored kit JSON (for repairs, resuming incomplete kits)

TOOLS PORTAL (password-gated):
  GET  /login         -> login form
  POST /login         -> password check, sets auth cookie
  GET  /tools         -> dashboard (Kit 25, Plan 90, Outbound Readiness Score, Leads)
  GET  /tools/review  -> legacy review form (old campaigns)
  POST /api/review    -> {domain, first_name, last_name, company, force} -> review JSON + URLs

The API is split into analyze + per-prospect sequence + share so that NO single
request runs all five Claude sequence calls, which pushed the combined run past
Vercel's 60s function cap.

Env: ANTHROPIC_API_KEY, APOLLO_API_KEY, APOLLO_ENRICH=1,
     BLOB_READ_WRITE_TOKEN (auto-added when you enable Blob storage on Vercel),
     TOOLS_PASSWORD, TOOLS_SECRET (for password-gated tools portal).
"""
import os, re, pathlib, json
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
import capture, storage, report_html, auth, review, leads

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
def home(request: Request):
    # One app, two domains: tools.fareehafatima.com is the private portal,
    # kit.fareehafatima.com (and everything else) is the public capture kit.
    if request.headers.get("host", "").split(":")[0].startswith("tools."):
        return RedirectResponse("/tools", status_code=307)
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

        # Store both the HTML share page AND the kit JSON (so repairs can resume)
        share = storage.save_kit(kit["slug"], report_html.render(kit))
        json_saved = storage.save_kit_json(kit["slug"], kit)

        # Return the /k/<slug> path on our domain (renders inline) rather than
        # the raw blob URL (which downloads as an attachment).
        out = {"share_url": ("/k/" + kit["slug"]) if share else None, "slug": kit["slug"]}
        if not share:
            out["share_error"] = storage.last_error()
        elif not json_saved:
            # HTML saved but JSON didn't - not fatal, just log it
            out["json_warning"] = storage.last_error()
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
            storage.save_kit_json(kit["slug"], kit)  # also persist the JSON
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

@app.get("/api/kit/{slug}")
def get_kit_json(slug: str):
    """Retrieve the stored kit JSON for a domain. Useful for repairs and resuming
    incomplete kits without re-running analyze."""
    clean_slug = re.sub(r"[^a-z0-9]", "", slug.lower())
    kit_data = storage.fetch_kit_json(clean_slug)
    if kit_data:
        return JSONResponse(kit_data)
    return JSONResponse({"error": "no kit JSON found for that slug"}, status_code=404)

# ---------------------------------------------------------------- Tools Portal

def _check_auth(request: Request) -> bool:
    """Check if user is authenticated via cookie. Returns True if valid."""
    cookies = request.cookies
    return auth.is_authenticated(cookies)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = None):
    """Login form for tools portal."""
    if _check_auth(request):
        return RedirectResponse("/tools", status_code=302)

    html = (HERE / "web" / "login.html").read_text(encoding="utf-8")
    if error:
        html = html.replace("<!-- ERROR -->", f'<p class="error">{error}</p>')
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex"
    })

@app.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    """Check password and set auth cookie."""
    if auth.verify_password(password):
        cookie_name, cookie_value = auth.make_auth_cookie()
        response = RedirectResponse("/tools", status_code=302)
        response.set_cookie(
            key=cookie_name,
            value=cookie_value,
            max_age=auth.COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        return RedirectResponse("/login?error=incorrect", status_code=302)

@app.get("/tools", response_class=HTMLResponse)
def tools_dashboard(request: Request):
    """Dashboard with cards for Kit 25, Plan 90, ORS, Leads."""
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)

    html = (HERE / "web" / "tools" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex"
    })

@app.get("/tools/thumb", response_class=HTMLResponse)
def thumb_form(request: Request):
    """Offer Scorecard thumbnail tool form."""
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)

    html = (HERE / "web" / "tools" / "thumb.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex"
    })

@app.get("/tools/scorecard", response_class=HTMLResponse)
def scorecard_form(request: Request):
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)
    html = (HERE / "web" / "tools" / "scorecard.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

@app.get("/tools/review", response_class=HTMLResponse)
def review_form(request: Request):
    """Legacy review form (old GTM Nerd campaigns). New work: /tools/scorecard."""
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)

    html = (HERE / "web" / "tools" / "review.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex"
    })

class ReviewReq(BaseModel):
    domain: str
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    campaign: str = "na"
    force: bool = False

@app.post("/api/scorecard")
def generate_scorecard(request: Request, req: ReviewReq):
    """HEDWIG Outbound Readiness Scorecard. Stored at scorecards/<slug>.json.
    Page: https://hedwigandco.com/scorecard?c=<slug> (route is an AGENT_TASKS item)."""
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    slug = review.slugify(req.company or req.domain)
    path = f"scorecards/{slug}.json"
    blob_url = f"https://gzbaq0nk2iyh6nku.public.blob.vercel-storage.com/{path}"
    page_url = f"https://hedwigandco.com/scorecard?c={slug}"
    if not req.force:
        stored = storage.fetch_json(path)
        if stored:
            return JSONResponse({"cached": True, "slug": slug, "review": stored, "blob_url": blob_url, "page_url": page_url})
    try:
        data = review.generate_scorecard(domain=req.domain, first_name=req.first_name,
                                         last_name=req.last_name, company=req.company)
        if not storage.enabled():
            return JSONResponse({"error": "blob storage not enabled"}, status_code=500)
        if not storage.save_json(path, data):
            return JSONResponse({"error": f"failed to store scorecard: {storage.last_error()}"}, status_code=500)
        return JSONResponse({"cached": False, "slug": slug, "review": data, "blob_url": blob_url, "page_url": page_url})
    except review.ReviewError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.post("/api/review")
def generate_offer_review(request: Request, req: ReviewReq):
    """Legacy review (old GTM Nerd rubric). New work: /api/scorecard. Auth required."""
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = "fareehafatima.org" if req.campaign.lower() in ("eu", "europe", "uk", "org", "emea") else "fareehafatima.co"
    slug = review.slugify(req.company or req.domain)

    # Once-per-domain: serve stored unless force=true
    if not req.force:
        stored = storage.fetch_review(slug)
        if stored:
            blob_url = f"https://gzbaq0nk2iyh6nku.public.blob.vercel-storage.com/reviews/{slug}.json"
            return JSONResponse({
                "cached": True,
                "slug": slug,
                "review": stored,
                "blob_url": blob_url,
                "page_url": f"https://{site}/review?c={slug}"
            })

    try:
        # Generate review
        review_data = review.generate_review(
            domain=req.domain,
            first_name=req.first_name,
            last_name=req.last_name,
            company=req.company
        )

        # Store in Blob
        if not storage.enabled():
            return JSONResponse({
                "error": "blob storage not enabled (BLOB_READ_WRITE_TOKEN missing)"
            }, status_code=500)

        success = storage.save_review(slug, review_data)
        if not success:
            return JSONResponse({
                "error": f"failed to store review: {storage.last_error()}"
            }, status_code=500)

        blob_url = f"https://gzbaq0nk2iyh6nku.public.blob.vercel-storage.com/reviews/{slug}.json"

        return JSONResponse({
            "cached": False,
            "slug": slug,
            "review": review_data,
            "blob_url": blob_url,
            "page_url": f"https://{site}/review?c={slug}"
        })

    except review.ReviewError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

# ---------------------------------------------------------------- thumbnails

class ThumbReq(BaseModel):
    domain: str
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    force: bool = False

@app.post("/api/thumb")
def generate_thumb(request: Request, req: ThumbReq):
    """Generate both Offer Scorecard thumbnail variants for a prospect and
    store them in Blob. Auth required. Returns the /thumbs/ paths to embed:
    variant A (plain) = <slug>.jpg, variant B (face) = <slug>-face.jpg."""
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    import thumb, review as _rv
    slug = _rv.slugify(req.company or req.domain)
    names = {"plain": f"{slug}.jpg", "face": f"{slug}-face.jpg"}

    if not req.force:
        if storage.fetch_thumb(names["plain"]) and storage.fetch_thumb(names["face"]):
            return JSONResponse({"cached": True, "slug": slug,
                                 "plain": f"/thumbs/{names['plain']}",
                                 "face": f"/thumbs/{names['face']}"})
    try:
        images = thumb.generate(req.domain, req.first_name, req.last_name,
                                req.company or req.domain)
        out = {"cached": False, "slug": slug}
        for variant, data in images.items():
            url = storage.save_thumb(names[variant], data)
            if not url:
                return JSONResponse({"error": f"blob store failed: {storage.last_error()}"},
                                    status_code=500)
            out[variant] = f"/thumbs/{names[variant]}"
            out[variant + "_bytes"] = len(data)
        return JSONResponse(out)
    except thumb.ThumbError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        return JSONResponse({"error": str(e) or e.__class__.__name__}, status_code=500)

@app.get("/thumbs/{filename}")
def serve_thumb(filename: str):
    """Serve a stored thumbnail through our own domain (public: these are
    embedded in emails). Long cache; images are content-stable per slug."""
    if not re.fullmatch(r"[a-z0-9-]+\.jpg", filename):
        return JSONResponse({"error": "bad filename"}, status_code=400)
    data = storage.fetch_thumb(filename)
    if not data:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})

@app.get("/t")
def thumb_by_review_url(u: str = "", v: str = "plain"):
    """Serve a thumbnail from a review URL, so emails need no extra custom
    field: <img src="https://thumbs.fareehafatima.co/t?u={{review_url}}">.
    Extracts the slug from the review link's c= param. v=face for variant B."""
    m = re.search(r"[?&]c=([a-z0-9-]+)", u or "")
    if not m:
        return JSONResponse({"error": "no slug in u"}, status_code=400)
    filename = m.group(1) + ("-face.jpg" if v == "face" else ".jpg")
    data = storage.fetch_thumb(filename)
    if not data:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})

# ---------------------------------------------------------------- Lead management system (multi-client)

def _auth_or_401(request: Request):
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None

@app.get("/tools/leads", response_class=HTMLResponse)
def leads_page(request: Request):
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)
    html = (HERE / "web" / "tools" / "leads.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

@app.get("/api/leads/clients")
def leads_clients(request: Request):
    if (r := _auth_or_401(request)): return r
    return JSONResponse({"clients": leads.list_clients()})

@app.post("/api/leads/clients")
async def leads_add_client(request: Request):
    if (r := _auth_or_401(request)): return r
    body = await request.json()
    c = leads.add_client(body.get("client",""), body.get("name",""))
    return JSONResponse({"ok": True, "client": c})

@app.get("/api/leads/{client}")
def leads_get(request: Request, client: str):
    if (r := _auth_or_401(request)): return r
    doc = leads.load(client)
    return JSONResponse({"client": client, "name": doc.get("name"), "updated": doc.get("updated"),
                         "leads": list(doc["leads"].values()), "tests": leads.test_stats(doc),
                         "summary": leads.summary(doc), "storage_error": storage.last_error()})

@app.post("/api/leads/{client}/upsert")
async def leads_upsert(request: Request, client: str):
    """Body: {"leads": [ {...}, ... ]} — manual edits, never from sync."""
    if (r := _auth_or_401(request)): return r
    body = await request.json()
    doc = leads.load(client)
    n = 0
    for rec in body.get("leads", []):
        if leads.upsert(doc, rec, from_sync=False): n += 1
    ok = leads.save(client, doc)
    return JSONResponse({"ok": ok, "upserted": n, "error": None if ok else storage.last_error()})

@app.post("/api/leads/{client}/tests")
async def leads_tests(request: Request, client: str):
    """Body: {"id": "...", "name":..., "hypothesis":..., "variable":..., "variants":[...], "metric":..., "start":..., "end":..., "decision":...}"""
    if (r := _auth_or_401(request)): return r
    body = await request.json()
    doc = leads.load(client)
    tid = body.get("id") or re.sub(r"[^a-z0-9]+","-", (body.get("name") or "test").lower()).strip("-")
    cur = doc["tests"].get(tid, {})
    cur.update({k: v for k, v in body.items() if k != "id"})
    cur.setdefault("created", leads._now())
    doc["tests"][tid] = cur
    ok = leads.save(client, doc)
    return JSONResponse({"ok": ok, "id": tid, "error": None if ok else storage.last_error()})

@app.post("/api/leads/{client}/import")
async def leads_import(request: Request, client: str):
    """Body: {"csv": "<text>", "campaign": "optional", "source": "optional"} — generic lead CSV or Instantly Activity export."""
    if (r := _auth_or_401(request)): return r
    body = await request.json()
    doc = leads.load(client)
    counts = leads.import_csv(doc, body.get("csv",""), body.get("campaign",""), body.get("source","csv"))
    ok = leads.save(client, doc)
    return JSONResponse({"ok": ok, **counts, "error": None if ok else storage.last_error()})

@app.post("/api/leads/{client}/sync")
async def leads_sync(request: Request, client: str):
    """Pull from Instantly API v2. Key from INSTANTLY_API_KEY env (or body.api_key for a one-off)."""
    if (r := _auth_or_401(request)): return r
    body = await request.json() if request.headers.get("content-type","").startswith("application/json") else {}
    key = body.get("api_key") or os.environ.get("INSTANTLY_API_KEY","")
    if not key:
        return JSONResponse({"ok": False, "error": "INSTANTLY_API_KEY not set"}, status_code=400)
    doc = leads.load(client)
    report = leads.sync_instantly(doc, key, body.get("campaign_ids"))
    ok = leads.save(client, doc)
    return JSONResponse({"ok": ok, **report, "error": None if ok else storage.last_error()})

@app.get("/tools/leads.csv")
def leads_csv(request: Request, client: str = "hedwig"):
    if not _check_auth(request):
        return RedirectResponse("/login", status_code=302)
    doc = leads.load(client)
    return Response(leads.to_csv(doc), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{client}-leads.csv"', "Cache-Control": "no-store"})
