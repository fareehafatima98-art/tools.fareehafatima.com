# Tools Portal Setup Instructions

## Overview
The tools portal is now implemented at `tools.fareehafatima.com` with password authentication, dashboard, and the Outbound Readiness Score (ORS) tool.

## Required Environment Variables

Add these to Vercel project settings (Settings → Environment Variables):

1. **TOOLS_PASSWORD** — The shared password for portal access
2. **TOOLS_SECRET** — Secret key for HMAC cookie signing (generate with: `openssl rand -hex 32`)

The following existing variables are already configured:
- ANTHROPIC_API_KEY
- APOLLO_API_KEY  
- APOLLO_ENRICH
- BLOB_READ_WRITE_TOKEN

## DNS Configuration

Add this domain to the Vercel project:

1. In Vercel dashboard: Project Settings → Domains → Add Domain
2. Enter: `tools.fareehafatima.com`
3. Vercel will show the DNS record to add in Cloudflare

**In Cloudflare DNS (for fareehafatima.com):**

Add a CNAME record:
- **Type:** CNAME
- **Name:** tools
- **Target:** cname.vercel-dns.com
- **Proxy status:** DNS Only (grey cloud) ← Important: Vercel docs require DNS-only for custom domains

## Routes

### Public (no auth required)
- `/` — Kit 25 (existing ICP capture flow)
- `/kestrel` — Public sample
- `/k/{slug}` — Kit share pages
- `/api/analyze`, `/api/sequence`, `/api/share`, `/api/capture` — Kit API

### Protected (password-gated)
- `/login` — Login form
- `/tools` — Dashboard (Kit 25, Plan 90, ORS, Leads cards)
- `/tools/scorecard` — ORS form (`/tools/review` is the legacy review form)
- `/api/review` — Generate review (POST with auth check)

## ORS Flow

1. User enters domain + optional name/company at `/tools/review`
2. POST `/api/review` → scrapes up to 5 pages, Haiku extracts facts, Sonnet scores against rubric
3. Review JSON stored at `reviews/{slug}.json` in Vercel Blob (public)
4. Returns:
   - `blob_url`: Direct JSON URL (e.g., `https://gzbaq0nk2iyh6nku.public.blob.vercel-storage.com/reviews/una-ai.json`)
   - `page_url`: Recipient-facing page (e.g., `https://fareehafatima.co/review?c=una-ai`)

### Recipient Page (Cloudflare Pages)

The review page at `fareehafatima.co/review?c={slug}` now has fallback logic:
1. Try local static file: `reviews/{slug}.json` (from the batch generator)
2. If 404, fall back to Blob URL: `{blob-base}/reviews/{slug}.json`

This means portal-generated reviews are **live instantly** at the fareehafatima.co URL with no Pages redeploy.

## Once-Per-Domain Cache

Like the kit flow, reviews are cached: if a review exists for a slug, it's served from storage unless `force: true` is passed.

## Cost
~$0.03 per review (Haiku extraction + Sonnet scoring with cached rubric).

## Testing Checklist

After deploy with the env vars set:

1. Visit `tools.fareehafatima.com` → should redirect to `/login`
2. Enter password → should redirect to `/tools` dashboard
3. Click "Outbound Readiness Score" → should show form at `/tools/review`
4. Generate a review for a test domain → should return JSON + URLs
5. Visit the `page_url` → should render the review page
6. Verify the Blob JSON URL is publicly accessible
7. Test force regenerate checkbox
8. Test once-per-domain caching (same domain without force should return cached)

## Files Changed

**New:**
- `auth.py` — Password check + cookie signing
- `review.py` — Review generation pipeline (ported from generate_reviews.py)
- `web/login.html` — Login form
- `web/tools/index.html` — Dashboard
- `web/tools/review.html` — Review form

**Modified:**
- `app.py` — Added /login, /tools, /tools/review, /api/review routes
- `storage.py` — Added fetch_review() and save_review()
- `requirements.txt` — Added requests>=2.31.0
- `GTM Consulting Campaign/website/review/index.html` — Added Blob fallback fetch

**No changes needed:**
- Kit flow routes (/, /kestrel, /k/{slug}, /api/*) unchanged
- Plan 90 flow (assumed to exist at /plan90) — if it doesn't, update the dashboard card
