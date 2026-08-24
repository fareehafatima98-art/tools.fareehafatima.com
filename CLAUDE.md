# CLAUDE.md — ICP Capture Kit

You are Claude Code, working on Fareeha's ICP Capture Kit. You share this project with
"Cowork Claude" (Claude in the Cowork desktop app), who handles strategy, Apollo campaign
work, and design direction. You handle code changes, deploys, and verification.

## What this project is
A hosted agent at kit.fareehafatima.com (Vercel, project `tools.fareehafatima.com`, team
`fareehas-projects-19fad08b`). A visitor enters a company domain. The agent:
1. Scrapes the company's site (incl. case-study/customers/resources/pricing pages).
2. Claude extracts REAL assets: product, ICP, named customers, case studies, lead magnets,
   free-trial URL, target locations. Never invents any of these.
3. Apollo pulls real prospects in that ICP (search is free; enrichment reveals full names +
   verified emails when APOLLO_ENRICH=1, ~1 credit/person, capped at 8 per run).
4. Claude writes a tailored 5-email sequence PER prospect (5 prospects = 25 emails).
5. The result is stored as a self-contained share page in Vercel Blob
   (kits/kit-<slug>.html) and its public URL returned as `share_url`. An existing stored
   kit = the once-per-domain limit (serve it instead of re-running; `force: true` overrides).

## Non-negotiables (do not undo these)
- Email quality bar lives in capture.py VOICE: 60-90 word bodies, at least one concrete
  real detail per email, no em dashes, no exclamation marks, no jargon, one soft CTA.
- Never fabricate customers, case studies, results, or facts about a prospect.
- Never write emails with a haiku-class model (there's a guard; keep it).
- Prospect enrichment stays capped and never runs without APOLLO_ENRICH=1.
- Do not pitch a company's own named customers back to them (filter in find_prospects).
- Booking: Calendly is embedded inline (calendly.com/hifareeha/discovery-meeting-with-fareeha),
  never a bare "let's talk" link. Fallback contact: hello@fareehafatima.com.
- VIDEO_EMBED stays empty until Fareeha records the video; render nothing when empty.
- Keys live only in Vercel env vars (ANTHROPIC_API_KEY, APOLLO_API_KEY, APOLLO_ENRICH,
  BLOB_READ_WRITE_TOKEN). Never commit keys. `.env` is gitignored.

## How you and Cowork Claude work together
The file `AGENT_TASKS.md` in this repo is the shared channel. Protocol:
1. Fareeha (or Cowork Claude via Fareeha) adds tasks under "## INBOX" with checkboxes.
2. When you start a session, read AGENT_TASKS.md FIRST. Do the inbox tasks top to bottom.
3. As you finish each task: tick it, move it under "## DONE" with a one-line result
   (what changed, files touched, and any URL/error output).
4. If something blocks you, move it to "## BLOCKED" with the exact error.
5. Commit AGENT_TASKS.md with your code changes and push. The push triggers the Vercel
   deploy, and the updated file is how Cowork Claude sees what happened.
6. After any change to the capture flow, verify: call the deployed /api/capture with a
   fresh test domain and record the share_url (or the error) in the DONE line.

Keep entries terse. This file is a log, not prose.
