"""
Outbound Readiness Score (HEDWIG) and legacy review pipeline (old GTM Nerd campaigns).

Ported from the old GTM Nerd generate_reviews.py.
This module scrapes a company site, extracts offer facts with Haiku, scores with
Sonnet against the rubric, and returns the review JSON.

Two-stage design (extraction = Haiku 4.5, scoring = Sonnet 5) keeps cost ~$0.03/prospect.
"""
import os, re, json, html, time
from typing import Dict, Any, Optional
import requests

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"

MAX_CHARS = 60_000
MAX_PAGES = 5
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; hedwig-ors/1.0; +https://fareehafatima.co)"

CANDIDATE_PATHS = [
    "", "/pricing", "/plans", "/product", "/platform",
    "/solutions", "/how-it-works", "/why-us", "/customers", "/about",
]

# ---------------------------------------------------------------- rubric

RUBRIC = """You are scoring a B2B company's commercial offer against ten criteria,
each out of 5. This is the Grand Slam Offer value equation merged with the practical
questions a cold-outreach campaign runs into.

1  Dream outcome — what the buyer actually wants, in their words, not the product's function
2  Perceived likelihood of achievement — why would they believe it works? named customers, logos, quotes
3  Speed to value — how fast is the first result, and is it in writing?
4  Effort and sacrifice — how much of the buyer's time and change does it cost?
5  Risk reversal — trial, guarantee, refund; what removes the downside?
6  Specific outcome — are the promises concrete and numeric, or adjectives?
7  Cost vs value — price against the cost of the status quo
8  Proof and differentiation — what is genuinely hard for a competitor to copy?
9  Offer clarity — could outreach and sales describe this offer identically?
10 Urgency and scarcity — any honest reason to start now rather than next quarter?

SCORING DISCIPLINE
- Verify before you downgrade. A guarantee stated plainly in the source is confirmed, not unverified.
- Represent the company's promises at full strength before assessing them. Understating them makes the review look uninformed.
- A zero is allowed and useful. Urgency is very often 0.
- Never invent a fact. If the source does not say it, it is absent, and absence is a finding.

SCOPE DISCIPLINE
- Stay in the GTM lane: packaging, naming, framing, urgency, clarity.
- Never recommend product, pricing-model, staffing or delivery changes. Convert those urges into questions and drop them.
- Never invent urgency. If no honest constraint exists, say the gap is on the buyer's calendar, not on a fake deadline.

VOICE
- Write as a colleague who read carefully, not a consultant grading homework.
- Frame every gap as cheap to test rather than broken.
- No em dashes. No exclamation marks. British or American spelling, be consistent."""

EXTRACT_PROMPT = """From the website text below, extract only what the company
actually states. Never infer, never embellish, never fill a gap with a plausible guess.
If something is absent, return an empty string or empty list. Absence is the finding.

Return strict JSON with exactly these keys:
{
  "what_they_sell": "one sentence",
  "buyer": "who they sell to, in their words",
  "dream_outcome_claimed": "the outcome they promise, quoted or closely paraphrased",
  "speed_claims": ["any statement about time to value, implementation time, setup speed"],
  "proof": ["named customers, logos, quantified results, certifications"],
  "guarantee_or_trial": "exact wording if present, else empty string",
  "pricing": "any pricing shown, else empty string",
  "cta": "what the site asks the visitor to do",
  "urgency": "any stated reason to act now, else empty string",
  "differentiator_claimed": "what they say makes them different",
  "adjective_promises": ["vague promises stated as adjectives rather than numbers"]
}

WEBSITE TEXT
---
{text}
---"""

SCORE_PROMPT = """{rubric}

Here is what the company states about its own offer, extracted from its website.

COMPANY: {company}
EXTRACT:
{extract}

Score all ten criteria, then choose the TWO changes that would move the most and are
cheapest to test. Both must be packaging, naming, framing, urgency or clarity.

Return strict JSON:
{{
  "scores": {{"1": n, "2": n, "3": n, "4": n, "5": n, "6": n, "7": n, "8": n, "9": n, "10": n}},
  "notes": {{"1": "one line citing what you saw", ...one per criterion...}},
  "suggestions": [
    {{"title": "the gap, stated as a sentence, no colon, under 14 words",
      "body": "2 to 3 sentences. Name what they currently say, why it costs them with this buyer, and what shape the fix takes. Do not prescribe exact copy."}},
    {{"title": "...", "body": "..."}}
  ]
}}

The two suggestion titles must not both be about the same criterion."""

# ---------------------------------------------------------------- scraping

TAG_RE = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>", re.S | re.I)
STRIP_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
NL_RE = re.compile(r"\n{3,}")

def clean_html(raw: str) -> str:
    """Strip tags and whitespace to get plain text."""
    t = TAG_RE.sub(" ", raw)
    t = re.sub(r"<(br|/p|/div|/li|/h[1-6])[^>]*>", "\n", t, flags=re.I)
    t = STRIP_RE.sub(" ", t)
    t = html.unescape(t)
    t = WS_RE.sub(" ", t)
    t = NL_RE.sub("\n\n", t)
    return "\n".join(ln.strip() for ln in t.splitlines() if ln.strip())

def scrape_domain(domain: str) -> str:
    """Scrape readable copy for a domain.

    Delegates to scrape_llm.scrape_site, the kit's tested scraper: plain fetches
    first, then the r.jina.ai reader proxy when the site turns out to be
    client-rendered (which is what made thrive-platform.com return 0 chars from
    a plain fetch). Returns "" when the site is genuinely unreadable, which the
    caller treats as a hard failure rather than scoring on nothing.
    """
    import scrape_llm
    d = re.sub(r"^https?://", "", domain).rstrip("/")
    return (scrape_llm.scrape_site(d) or "")[:MAX_CHARS]

# ---------------------------------------------------------------- Claude

def call_claude(model: str, prompt: str, max_tokens: int,
                cache_prefix: Optional[str] = None) -> str:
    """Make a Claude API call with optional prompt caching."""
    from anthropic import Anthropic
    client = Anthropic()

    blocks = []
    if cache_prefix:
        blocks.append({
            "type": "text",
            "text": cache_prefix,
            "cache_control": {"type": "ephemeral"}
        })
    blocks.append({"type": "text", "text": prompt})

    r = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": blocks}],
    )
    if getattr(r, "stop_reason", None) == "max_tokens":
        raise RuntimeError(
            f"model output truncated at max_tokens={max_tokens}; "
            "thinking tokens count against the budget, raise it")
    # content may lead with a ThinkingBlock; take the first text block.
    for block in r.content:
        if getattr(block, "type", "") == "text":
            return block.text
    raise RuntimeError("model response contained no text block")

def parse_json_response(s: str) -> dict:
    """Extract and parse JSON from a model response (strips fences if present)."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S)
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0) if m else s)

def call_claude_json(model: str, prompt: str, max_tokens: int,
                     cache_prefix: Optional[str] = None) -> dict:
    """Call the model and parse its JSON, retrying once with the parse error.

    Models occasionally emit invalid JSON (usually an unescaped quote inside a
    string, since the prompts encourage quoting the site's own copy). On a parse
    failure, show the model its output and the exact error and ask for corrected
    strict JSON. Costs one extra call in the rare failure case.
    """
    raw = call_claude(model, prompt, max_tokens, cache_prefix=cache_prefix)
    try:
        return parse_json_response(raw)
    except json.JSONDecodeError as e:
        repair = (
            "Your previous reply was invalid JSON and failed to parse.\n"
            f"Parser error: {e}\n\nYour reply was:\n{raw}\n\n"
            "Return the SAME content as strict, valid JSON only. Escape every "
            'double quote inside string values as \\". No code fences, no prose.'
        )
        return parse_json_response(call_claude(model, repair, max_tokens))

# ---------------------------------------------------------------- pipeline

def slugify(s: str) -> str:
    """Convert a company name to a slug for filenames and URLs."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")

def monogram(company: str) -> str:
    """Generate a 2-letter monogram from company name for logo fallback."""
    parts = [w for w in re.split(r"[^A-Za-z0-9]+", company) if w]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()

class ReviewError(Exception):
    """Raised when the review cannot be generated."""
    pass

# ---------------------------------------------------------------- Outbound Readiness Scorecard (HEDWIG)

SCORECARD_RUBRIC = """You are scoring how ready a B2B healthcare company's public offer is for
cold outbound. Ten criteria, each out of 5, judged only from what the company's own website says.
The question behind every criterion: could a cold email built from this site earn a reply from a
busy buyer who has never heard of them?

1  Buyer named — does the site say who it is for, in the buyer's words (role, care setting, size)? "Healthcare organizations" scores low.
2  Offer in one sentence — could a stranger repeat what they do and the result in one line?
3  Outcome is a number — is the promise numeric (hours saved, days to go-live, percentage lift) or adjectives?
4  Proof a cold reader believes — named customers, quantified results, quotes, clearances or certifications.
5  Speed to first value — how fast the first result lands, stated in writing.
6  Low-friction first step — is there an ask smaller than "book a demo" (pilot, evaluation unit, assessment, trial)? Outbound converts on the small yes.
7  Risk removed — guarantee, pilot terms, refund, anything that takes the downside off the buyer.
8  Differentiation in a sentence — one thing a competitor cannot honestly say.
9  One conversion path — a single primary call to action, or several competing ones.
10 Reason to act now — an honest constraint (regulatory date, capacity, pricing window) or none.

SCORING DISCIPLINE
- Verify before you downgrade. A guarantee or pilot stated plainly in the source is confirmed.
- Represent the company's promises at full strength before assessing them.
- A zero is allowed and useful. Criterion 10 is very often 0.
- Never invent a fact. If the source does not say it, it is absent, and absence is the finding.

SCOPE DISCIPLINE
- Stay in the outbound lane: who to write to, what to say, what to ask for, what proof to attach.
- Never recommend product, pricing-model, staffing or delivery changes.
- Never invent urgency.

VOICE
- Write as a colleague who read carefully, not a consultant grading homework.
- Frame every gap as cheap to test rather than broken.
- No em dashes. No exclamation marks. American spelling."""

SCORECARD_PROMPT = """Here is what the company states about its own offer, extracted from its website.

COMPANY: {company}
EXTRACT:
{extract}

Score all ten criteria, then choose the TWO changes that would most improve the reply rate of a
cold email campaign and are cheapest to test. Both must be about who to target, what to say,
what to ask for, or what proof to show.

Return strict JSON:
{{
  "scores": {{"1": n, "2": n, "3": n, "4": n, "5": n, "6": n, "7": n, "8": n, "9": n, "10": n}},
  "notes": {{"1": "one line citing what you saw", ...one per criterion...}},
  "verdict": "one sentence, under 16 words, the honest headline for this company's outbound readiness, no company name",
  "summary": "three sentences addressed to the reader as 'you'. First: what is strongest, cited. Second: the gap that costs the most replies. Third: what the two changes below would do. No em dashes, no exclamation marks.",
  "suggestions": [
    {{"title": "the gap, stated as a sentence, no colon, under 14 words",
      "body": "2 to 3 sentences. Name what they currently say, why it costs them replies with this buyer, and what shape the fix takes. Do not prescribe exact copy."}},
    {{"title": "...", "body": "..."}}
  ]
}}

The two suggestion titles must not both be about the same criterion."""

SCORECARD_CRITERIA = ["Buyer named", "Offer in one sentence", "Outcome is a number",
    "Proof a cold reader believes", "Speed to first value", "Low-friction first step",
    "Risk removed", "Differentiation in a sentence", "One conversion path", "Reason to act now"]

def generate_scorecard(domain: str, first_name: str = "", last_name: str = "",
                       company: str = "") -> Dict[str, Any]:
    """HEDWIG Outbound Readiness Scorecard. Same pipeline and JSON shape as generate_review,
    different rubric, different labels, kind="scorecard"."""
    text = scrape_domain(domain)
    if len(text) < 500:
        raise ReviewError(f"Scrape returned only {len(text)} chars - site may be unreadable or client-rendered")
    extract = call_claude_json(HAIKU, EXTRACT_PROMPT.replace("{text}", text), 2500)
    if not company:
        company = domain.replace("https://", "").replace("http://", "").replace("www.", "").split(".")[0].title()
    scored = call_claude_json(SONNET, SCORECARD_PROMPT.format(company=company, extract=json.dumps(extract, indent=2)),
                              6000, cache_prefix=SCORECARD_RUBRIC)
    sugg = scored.get("suggestions", [])[:2]
    if len(sugg) < 2:
        raise ReviewError(f"Model returned {len(sugg)} suggestions (expected 2)")
    scores = scored.get("scores", {})
    total = sum(int(v) for v in scores.values() if str(v).lstrip("-").isdigit())
    return {
        "kind": "scorecard",
        "brand": "HEDWIG",
        "slug": slugify(company),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "company": company,
        "monogram": monogram(company),
        "logo_url": f"https://logo.clearbit.com/{domain}",
        "video_url": "scorecard.mp4",
        "video_length": "0:58",
        "caption": "What we found, in under a minute.",
        "title": "Outbound Readiness Scorecard",
        "heading": "Two things that would lift your reply rate first",
        "suggestions": sugg,
        "calendly": "https://calendly.com/hifareeha/discovery-meeting-with-fareeha",
        "generated": time.strftime("%Y-%m-%d"),
        "sources": [domain],
        "criteria": SCORECARD_CRITERIA,
        "total": total,
        "band": "ready" if total >= 35 else ("close" if total >= 20 else "early"),
        "verdict": scored.get("verdict", ""),
        "summary": scored.get("summary", ""),
        "_scores": scores,
        "_notes": scored.get("notes", {}),
        "_extract": extract,
    }

def generate_review(domain: str, first_name: str = "", last_name: str = "",
                   company: str = "") -> Dict[str, Any]:
    """
    Legacy review (old rubric). New work uses generate_scorecard.

    Args:
        domain: Company domain to scrape
        first_name: Recipient first name (optional)
        last_name: Recipient last name (optional)
        company: Company name override (if empty, extracted from scrape)

    Returns:
        Review dict matching the una-ai.json schema

    Raises:
        ReviewError: If scrape yields <500 chars or model returns invalid data
    """
    # 1. Scrape
    text = scrape_domain(domain)
    if len(text) < 500:
        raise ReviewError(f"Scrape returned only {len(text)} chars - site may be unreadable or client-rendered")

    # 2. Extract with Haiku
    extract_prompt = EXTRACT_PROMPT.replace("{text}", text)
    extract = call_claude_json(HAIKU, extract_prompt, 2500)

    # If company not provided, try to infer from domain
    if not company:
        # Simple heuristic: capitalize first part of domain
        company = domain.replace("https://", "").replace("http://", "") \
                        .replace("www.", "").split(".")[0].title()

    # 3. Score with Sonnet (rubric is cached)
    score_prompt = SCORE_PROMPT.format(
        rubric="",  # empty since it's in cache_prefix
        company=company,
        extract=json.dumps(extract, indent=2)
    )
    scored = call_claude_json(SONNET, score_prompt, 6000, cache_prefix=RUBRIC)

    # 4. Build review document
    sugg = scored.get("suggestions", [])[:2]
    if len(sugg) < 2:
        raise ReviewError(f"Model returned {len(sugg)} suggestions (expected 2)")

    slug = slugify(company)

    review = {
        "slug": slug,
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "company": company,
        "monogram": monogram(company),
        "logo_url": f"https://logo.clearbit.com/{domain}",
        "video_url": "../review.mp4",
        "video_length": "0:58",
        "caption": "What I found, in under a minute.",
        "heading": "Two things I'd change first",
        "suggestions": sugg,
        "calendly": "https://calendly.com/hifareeha/discovery-meeting-with-fareeha",
        "generated": time.strftime("%Y-%m-%d"),
        "sources": [domain],
        "_scores": scored.get("scores", {}),
        "_notes": scored.get("notes", {}),
    }

    return review
