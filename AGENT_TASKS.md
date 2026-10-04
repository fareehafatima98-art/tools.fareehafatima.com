# AGENT_TASKS — shared channel between Cowork Claude and Claude Code

Protocol: Claude Code reads this FIRST every session. Do INBOX top to bottom. Move finished
items to DONE with a one-line result (files touched + test output/URL). Blockers go to
BLOCKED with the exact error. Commit this file with your changes.

## INBOX

- [ ] DEPLOY HEDWIG SITE (static, 5 files, already in this repo under `hedwig/`): create a NEW Vercel project `hedwigandco` in team fareehas-projects-19fad08b from this repo with Root Directory = `hedwig`, framework = Other (static, no build). Add domains hedwigandco.com and www.hedwigandco.com to it (DNS already points at Vercel: A 76.76.21.21, www CNAME cname.vercel-dns.com, set 28 Sep). Verify https://hedwigandco.com loads index, case-study, pricing, about, and that the Calendly embed renders on index and pricing. Note the production URL here. Do NOT touch the kit.fareehafatima.com project.
- [ ] KIT 25 TIMES OUT ON VERCEL: POST /api/capture returns 504 FUNCTION_INVOCATION_TIMEOUT at 60s (tested cerve.com, axya.co, brandnudge.com on 22 Sep). Cowork Claude bumped vercel.json maxDuration 60->300 (Pro allows it). Push, then verify /api/capture on cerve.com returns a share_url and note it here. If it still exceeds 300s, split capture into two calls (analyze -> sequence) from the front end.
- [ ] MANUAL-REPLY TRACKING (opens + clicks for emails Fareeha sends by hand from Gmail, outside Instantly): add two tiny public endpoints in app.py, no auth: (1) GET /px/{lead}.gif -> logs {lead, ts, ua, ip-hash} and returns a 1x1 transparent GIF, Cache-Control: no-store; (2) GET /go/{lead}?to=<url> -> logs a click then 302s to `to` (allowlist fareehafatima.co/.org/kit.fareehafatima.com only). Store events as append-only JSON lines in Blob (events/{lead}.jsonl, same storage.py pattern). (3) GET /tools/engaged (auth) -> table: lead, first open, opens, first click, clicks, last seen, kit link. `lead` is a slug Fareeha puts in the email by hand, e.g. <img src="https://kit.fareehafatima.com/px/toni-cerve.gif" width=1 height=1> and https://kit.fareehafatima.com/go/toni-cerve?to=https://kit.fareehafatima.com/k/cerve. Gmail proxies images so opens are approximate; clicks are exact. Verify with a test send to Fareeha's own inbox and log the result here.
- [ ] MIGRATE OFF VERCEL BLOB (cost): Vercel suspended the Hobby blob store on Sep 15 (all reads 403) and Fareeha had to upgrade to Pro mid-launch. Move review/thumb storage to Cloudflare R2 (S3-compatible; she already uses Cloudflare; free tier covers our ~1GB + egress-free serving). Scope: (1) storage.py: swap vercel_blob calls for boto3/S3 against R2 (env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET), keep save_review/fetch_review/save_thumb/fetch_thumb signatures identical; (2) serve via an R2 public bucket or custom domain, update the blob-base meta tag in the review page template and any hardcoded gzbaq0nk2iyh6nku URLs in app.py/review.py/web/; (3) one-time copy script for existing blobs (reviews/*.json, thumbs/*.jpg, kits/*.html) Vercel->R2, run AFTER Pro unblocks reads; (4) verify /t, /review?c=, /api/review, /api/thumb end to end on a test slug, then Fareeha can downgrade Vercel back to Hobby. Do NOT break live campaigns: keep Vercel paths working until R2 verified, then flip.


- [ ] (Fareeha, THE ONLY THING BLOCKING TRACKING) `git push origin main` from your Terminal.
      Unpushed: 35fac2a (unreadable-site guard + scrape fallback), 9f07d8c (analytics snippet +
      the /_vercel rewrite fix + share guard), plus the quote/statistics rule and log commits.
      The frescoai kit did NOT need them (fresco.build scrapes fine on the deployed scraper), but
      NO page counts a visit until 9f07d8c is live. CORRECTION to my earlier note
      that pushes now land by themselves: something did auto-commit and auto-push three times
      between 11:44 and 12:11 today (that is how 0f7512e finally shipped), then it stopped. My own
      push still fails, now with "could not read Username for https://github.com: Device not
      configured" (credential.helper=osxkeychain, but no tty to unlock it).
- [ ] (Fareeha) QC the 25 emails: https://kit.fareehafatima.com/k/edexia (renders inline, 25
      emails across 5 unique-company AU buyers, no dead links).

## BLOCKED

- [x] RESOLVED same session (Fareeha added funds, frescoai regen then ran normally).
      ANTHROPIC API CREDITS EXHAUSTED — this blocks every regeneration, not just
      frescoai. Exact error from prod, on both /api/analyze and /api/sequence:
      `Error code: 400 - {'type': 'invalid_request_error', 'message': 'Your credit balance is too
      low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase
      credits.'}` (request_id req_011CdNXZdNuqaMFp2TWLnhhj). /api/sequence still answers HTTP 200
      with emails:[] and the reason in `error`, so the front-end shows an empty tab rather than a
      clear message — worth surfacing better once credits are back. Top up, then the frescoai
      regen (analyze fresco.build force + 5 sequences + share as frescoai and fresco) is ready to
      run; the scripts are in the scratchpad.
- [ ] Push from Claude Code's env: still fails ("could not read Username ... terminal prompts
      disabled") for both https and ssh — no cached creds, no ~/.ssh key, no gh CLI, and `!` has
      no interactive prompt. Pushes must come from Fareeha's Terminal.app (that is how 3509b9e
      reached prod). Local commits are always staged and ready; see the INBOX push item.

## DONE

- [x] (Claude Code 24 Aug) KIT JSON PERSISTENCE complete, commit fadb14b. /api/share and /api/capture
      now store BOTH kit-<slug>.html and kit-<slug>.json in Blob. New GET /api/kit/{slug} returns
      the stored JSON. Added storage.fetch_kit_json() and save_kit_json(). JSON save failure is
      non-fatal (logged as json_warning). Enables repairs and resuming incomplete kits without
      re-running analyze. Files: app.py, storage.py.
- [x] (Claude Code 24 Aug) TOOLS PORTAL COMPLETE, commit 9841fbf. Files: auth.py (password check +
      HMAC cookies), review.py (scrape → Haiku extract → Sonnet score pipeline, ported from
      generate_reviews.py), app.py (+/login, /tools, /tools/review, /api/review routes),
      storage.py (+fetch_review/save_review), requirements.txt (+requests), web/login.html,
      web/tools/index.html (dashboard), web/tools/review.html (form). Modified "GTM Consulting
      Campaign/website/review/index.html" to fall back to Blob URL after local 404 (meta tag with
      blob-base, try local first then {base}/reviews/{slug}.json). TOOLS_PORTAL_SETUP.md documents
      env vars (TOOLS_PASSWORD, TOOLS_SECRET), DNS (CNAME tools → cname.vercel-dns.com, grey cloud),
      and routes. Once-per-domain cache + force checkbox working. No verification yet (needs env
      vars + DNS + push to deploy). Dashboard links to /, /plan90, /tools/review.
- [x] (Claude Code) frescoai REBUILT AND LIVE, garbage gone: https://kit.fareehafatima.com/k/frescoai
      (and https://kit.fareehafatima.com/k/fresco, since fresco.build's natural slug is "fresco").
      25/25, 5 per tab, 0 dead links, 0 occurrences of Bill Gates / Larry Fink / Satya Nadella /
      BlackRock / Microsoft / Breakthrough Energy. Your domain correction was the fix: fresco.build
      scrapes 9269 chars even on the OLD deployed scraper. Brief matches your ground truth: company
      "Fresco", Division 8 door/frame/hardware takeoffs reconciling schedules, plans and specs;
      buyer_titles estimator / senior estimator / owner / chief estimator / preconstruction /
      BD; named_customers and case_studies both EMPTY (every site testimonial is anonymous) so the
      customer-claim rules kept the emails honest; proof_points are the real anonymous quotes plus
      SOC 2 Type 2. Prospects are all US Division 8: Dwayne Wells (Owner/Estimator, Liberty Glass,
      GA), Hanah Hood (Preconstruction Manager, SHORE TOTAL, Denver), Danika Kain (BD Manager,
      Hanover Specialties, VA), Benjamin Perez (Estimator, BREX Commercial Door, TX), Daniel Rosen
      (Estimator, Benco Inc., NJ). ~8 Apollo credits, ~$0.45 API (the extra over estimate is the
      email-3 rework below). Kit JSON: scratchpad/fresco_kit.json.
      ENGINE, steps 1+2 (35fac2a, PUSH PENDING): SiteUnreadable guard in analyze - under 500 chars
      of text, or no company/product_summary, fails the run BEFORE find_prospects, so a blank brief
      can never spend Apollo credits again; /api/analyze returns 422 with the reason instead of 500;
      /api/share refuses to store a kit with no brief or no emails (the stored page IS the cache,
      which is why the garbage kit kept being served); scrape fallback = extra static paths then the
      r.jina.ai reader proxy (fresco-ai.com goes 0 -> 2663 chars this way), both wall-clock budgeted
      so analyze still fits 60s; foreai.co and edexia.com unchanged and never touch the proxy. Also
      fixed clean_domain's lstrip("www.") - a character-set strip that turned wow.com into ow.com.
      QC caught real defects in the first pass that mechanical checks miss, all in email 3, all from
      quoting the site's ONE hedged anonymous testimonial ("this might have saved us on a job in
      Denver where we missed 200 doors"): one email upgraded "might have" to "would have", two wrote
      the quote's first person in Fareeha's voice ("we missed 200 doors"), one announced "we do not
      have a named case study", and one invented "our aggregate data shows most Division 8
      estimators...". Fixed by regenerating only email 3 for the three affected prospects against
      new permanent QUOTE and STATISTICS rules in capture.py (keep a hedge on its own clause, never
      speak a quote's first person, attribute anonymous quotes by role/company type, and state no
      number or aggregate that is not in proof_points - no "our data shows", no invented
      percentages). Final QC on all 25 is clean: no fabricated claim, no misquote, 55-95 word
      bodies, no em dashes or exclamation marks, correct openers, no dead links (asset is null
      throughout - Fresco publishes no lead-magnet or trial URL, so every email refers to the free
      takeoff by name in prose).
- [x] (Claude Code) Page-visit tracking CODE COMPLETE, waiting on a push to go live (commit
      9f07d8c, see BLOCKED). Snippet added to
      report_html's rendered share pages and web/index.html, and /k/{slug} injects it into
      already-STORED pages on the way out (idempotent), so edexia, openhive, foreai and bowe
      start counting with no re-render and no blob rewrites. I did not re-share the four kits as
      written: serve-time injection covers their existing links immediately, and re-rendering
      three of them would have meant parsing emails back out of HTML (lossy) since kit JSON is
      not stored yet.
      THE SNIPPET ALONE WOULD HAVE TRACKED NOTHING: vercel.json rewrote /(.*) to our function, so
      kit.fareehafatima.com/_vercel/insights/script.js AND the /_vercel/insights/view beacon both
      returned FastAPI's {"detail":"Not Found"} (verified with curl before changing anything). The
      rewrite now excludes /_vercel/. Enable Web Analytics in the Vercel dashboard and the script
      will start returning 200 on its own.

- [x] (Claude Code) URGENT foreai REBUILD done: https://kit.fareehafatima.com/k/foreai is now
      25/25 (5 per tab, original tab order) with ZERO mention of Citi/HSBC/Scotiabank/Discover/
      Intesa/Standard Chartered anywhere on the page. Verified your read of foreai.co first: those
      six brands appear only under "Explore live test cases ... See in action"; the trusted-by row
      is Google, UBS, Sixt, NZZ, SMG, Uber (+ onlinefuels.de, a 7th logo you did not list — say if
      you want it in named_customers). 0 Apollo credits (prospects reused verbatim from the live
      page), ~$0.30 API.
      ENGINE (capture.py, permanent, COMMITTED BUT UNPUSHED): (1) CUSTOMER_EVIDENCE_RULE in the
      extract_assets prompt — a brand counts as a customer only via trusted-by / testimonial /
      case study, and is EXCLUDED when it appears in demo content, sample test cases, "see in
      action" walkthroughs, screenshots or integration lists; (2) CUSTOMER CLAIM RULE in the
      sequence prompt — only named_customers may be called customers, and a result/metric/quote
      may not be attached to one unless that exact pairing is in case_studies; email 3 falls back
      to aggregate proof_points when case_studies is empty instead of inventing a case study.
      Both prompts render-tested with stubbed deps.
      ROOT CAUSE of Tony's empty tab (not rate limits): with a company name in Hebrew, the model
      answered in Hebrew, which is enough extra tokens to blow the 60s cap. Six consecutive 504s;
      adding one "write in ENGLISH" line landed it in 16.1s. That line is now in VOICE, so it is
      fixed for every future non-Latin prospect. Also seen: firing all 5 /api/sequence calls at
      once 504s more than running them one at a time (3/5 concurrent vs 5/5 serial).
      CONTENT: first pass was 25/25 but 4 of the email 3s still invented Sixt/UBS/Google outcomes
      ("how Sixt cut testing time without adding headcount"), so those four were regenerated with
      the sharper rule and only email 3 swapped in, keeping the QC-passed 1/2/4/5 verbatim. Final
      QC on all 25: no forbidden brand, no fabricated customer result (customers named as
      customers only, 90%/10x stated as aggregate), 74-95 word bodies, no em dashes, no
      exclamation marks, correct "Hi <first>," openers, 0 dead links (only real assets:
      tools.foreai.co/roi-calculator, app.foreai.co), inline Calendly, no video block.
      Kit JSON kept at scratchpad/foreai_kit.json until the /api/kit/{slug} task below lands.
- [x] (Claude Code) Engine rule hardened in two more passes, because live tests showed the first
      version was too soft. Prod with rule v1 still wrote "How UBS and Sixt handle QA at scale /
      UBS runs on fore ai for exactly that reason" (invents how and why a real customer uses it),
      so v2 (8f424d0) allows ONLY the bare fact that a named_customer is a customer unless
      case_studies has that exact pairing, and names those observed phrasings as fabrications.
      Verified live after deploy: bodies came back honest ("companies like UBS and Sixt run on it",
      90%/10x stated as aggregate). One gap remained, the subject line "Why Google and UBS run QA
      differently now", so v3 (1d7ba80) forbids a customer name in ANY subject when case_studies
      is empty. v3 (pushed as 9ec9f3c) verified live on 2 fresh sequences, 10 subjects: no invented
      customer story anywhere, and 9 of 10 subjects name no customer. The one that did was
      "Companies like Uber and Sixt run this way", which states only the bare true fact, so I left
      the rule as is rather than tighten further: the no-name-in-subject line is a proxy for the
      real bar (no promise the body cannot honour) and that bar held. Nothing outstanding here.
- [x] (Claude Code) REPAIRED openhive to 25/25 without a full rerun (0 Apollo credits, ~$0.10 API).
      Parsed Riley's + Wayne's existing about + 5 emails each out of the live /k/openhive HTML and
      kept them verbatim; POSTed /api/sequence for the 3 failed prospects (Kushal Magar/SyncGTM 5,
      Adir Zimerman/Rainmakers 5, Vic Ahmed/PitchStart 5 — all landed first try, 28-57s); assembled
      the kit in the original tab order [Kushal, Adir, Riley, Vic, Wayne] and POSTed /api/share.
      Verified live: https://kit.fareehafatima.com/k/openhive now shows 25 emails across 5 tabs
      (5 each), 0 dead links, Riley's/Wayne's original subjects intact. share_error=None.
- [x] (Claude Code) CONFIRMED 25/25 LIVE on prod. edexia now renders a full, clean kit at
      https://kit.fareehafatima.com/k/edexia — 25 emails across 5 unique-company AU buyers
      (David Shaw/CREST, Dianne Bryant/Illawarra Grammar, Trish Stockbridge/Kambala, Bruce
      McNalty/Townsville Grammar, Tahira Hussain/Wisdom), 0 dead asset links, inline text/html
      (200, no attachment). One sequence 504'd at 61s on first try and the retry landed it in 30s
      (5/5) — structured outputs (valid JSON, ~16-30s/call) + one retry = reliable 25/25.
      This confirm reused saved prospects, so it cost ~0 Apollo credits.
- [x] (Claude Code) Front-end retry (0f7512e): fetchSequence retries a failed/empty /api/sequence
      once, recovering the occasional single-call 60s 504. JS parses clean. Unpushed (see INBOX) —
      not required for the current kit, needed for real browser users.
- [x] (Claude Code) JSON-validity fix (1ba3ad2): write_prospect_sequence now uses structured
      outputs (output_config json_schema, SEQUENCE_SCHEMA) so the API guarantees valid JSON —
      eliminates the unescaped-quote / no-JSON parse failures that capped run 3 at 15/25. Graceful
      fallback to the tolerant parser if structured outputs are unavailable (old SDK / model /
      transient) so it never regresses. Unit-tested all four paths + schema validity.
- [x] (Claude Code) Timeout fix committed: reverted write_prospect_sequence max_tokens 4000->2600
      (871e37a) after live regenerates 504'd on individual /api/sequence calls at ~60s; plus
      front-end fan-out stagger + shorter retry backoff (0ee0cdc). Confirmed live: no more 504s.
- [x] (Claude Code) QC fixes committed (3eabe6a), all four, with tests: (1) dedupe by company +
      buyer-title preference (apollo per_page=25 + location fields; capture.dedupe_by_company /
      title_score) so no two prospects share an org and practitioners lose to buyers; (2)
      target_locations enforced (capture._enforce_locations), relaxed only if <top_n match; (3)
      no dead links — sequence prompt emits "asset" only with a real url else null+prose, and
      report_html + web skip empty/#/<> anchors (valid_asset_url/validUrl); (4) /k/{slug} now
      serves the blob inline as text/html (no-cache) and every share_url is the /k/<slug> path
      on our domain (fixes the "link downloads a file" issue). Files: apollo.py, capture.py,
      storage.py (fetch_kit_html), report_html.py, app.py, web/index.html. Awaiting push +
      edexia regenerate (see INBOX).
- [x] (Claude Code) LIVE RE-TEST PASSED on the split flow (prod, main @ 2fd4282, edexia.com force).
      /api/analyze 14.8s -> 5 prospects. 5x /api/sequence in parallel, all http=200, 5 emails each
      = 25/25 emails (longest single call 57.4s, under the 60s cap; the others 18-30s). /api/share
      0.9s -> share_url with share_error=None (blob token now correct).
      SHARE URL: https://gzbaq0nk2iyh6nku.public.blob.vercel-storage.com/kits/kit-edexia.html
      Verified: page loads (200, 25KB, tabs+emails+inline Calendly, title "ICP Capture Kit —
      Edexia"); /k/edexia now 307-redirects to it; /api/analyze without force returns cached=True
      with the share_url (once-per-domain cache working). No 60s timeout anywhere. Fareeha can QC
      the 25 emails at the share URL above.
- [x] (Claude Code) URGENT — split the API so no request runs all 5 sequences (commit 07bf05f).
      The combined /api/capture run was blowing Vercel's 60s cap (plain-text timeout page).
      Now: POST /api/analyze {domain,force} = scrape + assets + enriched prospects (fast half,
      keeps the once-per-domain cache check); POST /api/sequence {assets,prospect} = one
      prospect's 5-email kit; POST /api/share {kit} = render + Blob store -> share_url
      (surfaces share_error). capture.build_kit refactored into analyze() + sequence_for()
      (kept as the CLI path). web/index.html rewritten: analyze, render tab shell with pending
      panes, fan out /api/sequence for all prospects IN PARALLEL filling each tab as it lands,
      then /api/share for the link; per-prospect + share errors surfaced inline. /api/capture
      kept for CLI/back-compat. Files: app.py, capture.py, web/index.html. Verified: endpoint
      tests (analyze cache miss/hit/force, sequence, share ok/403/disabled), sequence_for
      failure capture, and front-end JS parses clean. Needs live re-test after push+deploy.
- [x] (Claude Code) JSON-robustness fix committed (b8697df) for the 4/5 empty sequences that
      Cowork Claude's prod test traced to JSON parse failures (not rate limits). scrape_llm:
      extract_json now strips a ```json fence, decodes from the first brace with raw_decode
      (tolerates trailing prose), and parses strict=False (literal newlines/tabs in bodies no
      longer break it); new llm_json helper adds ONE retry on a parse failure (empty/refused/
      malformed), separate from llm()'s HTTP retry. capture: write_prospect_sequence uses
      llm_json, max_tokens 2600->4000, and instructs valid JSON with no inner double-quotes;
      extract_assets routed through llm_json too. Per-prospect error surfacing + totals kept.
      Unit-tested extract_json (newlines/tabs/fences/trailing-junk/empty) and the llm_json retry.
      Needs live re-test after main deploys to confirm 25/25.
- [x] (Claude Code) Decision 2 — 25-email rate-limit resilience committed (3d4f1ff). llm() does
      one jittered-backoff retry on transient 429/529/5xx; build_kit staggers the concurrent
      prospect-sequence starts (STAGGER_SECONDS=0.8/index) and stores per-prospect errors.
      (Prod test confirmed no 429s remained; the residual failures were JSON, fixed above.)
- [x] (Claude Code) Decision 1 — merged deploy-branch tip into main (clean fast-forward, no
      force). Confirmed prod branch is main: every production deploy has githubCommitRef=main;
      pushing main auto-deploys prod (no manual promotion). main up to 3509b9e is now live.
- [x] (Claude Code) TASK 1 hybrid sync done. git-init'd folder, added remote, synced FROM the
      deploy branch (no force-push). Original premise was backwards: local was OLDER, missing
      api/index.py + vercel.json and behind on the Apollo endpoint (old /v1 path 403s),
      concurrent sequences, and the read-only-FS guard. All v3.1 features present; nothing to
      port. Added CLAUDE.md + AGENT_TASKS.md to the repo; gitignored .claude/ and .vercel.
- [x] (Claude Code) Verified live capture end to end (all but share link). stripe.com ~45s,
      edexia.com (force) with 5 real enriched AU teacher prospects + verified emails. Confirms
      ANTHROPIC_API_KEY, APOLLO_API_KEY, APOLLO_ENRICH=1 working, maxDuration=60 in vercel.json.
- [x] (Cowork Claude) Built v3.1 feature set; found GitHub already carried the newer Vercel
      plumbing. Task 1 rewritten to hybrid-sync instead of force-push. Claude Code's catch — correct.

## DONE (Cowork Claude, 2026-09-03)
- [x] Added Offer Scorecard thumbnail system: thumb.py (mShots fetch w/ placeholder polling,
  Pillow composite, variants plain/face), storage.save_thumb/fetch_thumb, POST /api/thumb
  (auth, cached per slug, force overrides), GET /thumbs/<file> (public, 24h cache).
  Assets: assets/face.jpg + DejaVu fonts. Pillow added to requirements.txt.
  Purpose: A/B split test in Instantly link email — variant A embeds /thumbs/<slug>.jpg,
  variant B /thumbs/<slug>-face.jpg, both linking to the review page. Fareeha pushes.
- [x] Added /tools/thumb UI page (web/tools/thumb.html) + dashboard card: manual thumbnail
  generation form -> /api/thumb, previews both variants with copy-URL buttons. Fareeha pushes.
- [x] Added GET /t?u=<review_url>&v=plain|face — serves the thumbnail by extracting the slug
  from the lead's existing review_url, so Instantly needs NO new custom field / no re-import.
