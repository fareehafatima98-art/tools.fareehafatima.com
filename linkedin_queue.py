#!/usr/bin/env python3
"""
linkedin_queue.py — today's LinkedIn touches, from an Instantly lead export. No automation.

Reads:  one or more Instantly lead exports (Campaign > Leads > Export; they carry the custom
        fields linkedIn, custom_opener, scorecard_url, ors_total), plus any "*instantly upload*.csv"
        found under Hedwig & Co as a fallback, and LEADS/linkedin-status.csv (what you already did).
Writes: "LEADS/LinkedIn today.csv" with two sections:
        CONNECT  (max 20): email 1 sent at least 1 day ago, no request yet. Opens and clicks first.
        MESSAGE  : request accepted, not yet messaged, with the DM text ready to paste.

Mark what you did:
  python3 linkedin_queue.py --requested a@x.com b@y.com
  python3 linkedin_queue.py --accepted a@x.com
  python3 linkedin_queue.py --messaged a@x.com
  python3 linkedin_queue.py --skip a@x.com
  python3 linkedin_queue.py --follow a@x.com      # no Connect button, you pressed Follow instead
  python3 linkedin_queue.py --closed a@x.com      # no Connect and no Follow (locked profile)
Followed and closed profiles come back into CONNECT after 14 days so you can re-check
whether the button has appeared (it does, once you share more connections).
Then rebuild the queue:
  python3 linkedin_queue.py --export ~/Downloads/leads.csv [--export another.csv] [--cap 20]
"""
import argparse, csv, glob, os, sys
from datetime import datetime, timezone, timedelta

BASE = os.path.expanduser("~/Claude/Hedwig & Co")
ICP = os.path.join(BASE, "LEADS")
STATUS = os.path.join(ICP, "linkedin-status.csv")
OUT = os.path.join(ICP, "LinkedIn today.csv")

DM_NEW = ("Thanks for connecting, {first}. I sent {company}'s outbound readiness score over by email "
          "last week, {total}/50. Happy to walk you through the two fixes if useful.")
DM_SEPT = ("Thanks for connecting, {first}. You looked at the outbound kit we sent {company} in September. "
           "I have since moved everything under Hedwig and would like to show you what changed.")

def norm(e): return (e or "").strip().lower()

def load_status():
    st = {}
    if os.path.exists(STATUS):
        for r in csv.DictReader(open(STATUS, encoding="utf-8")):
            st[norm(r["email"])] = r
    return st

def save_status(st):
    cols = ["email", "requested", "accepted", "messaged", "skipped", "followed", "closed", "note"]
    with open(STATUS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for e in sorted(st): w.writerow({c: st[e].get(c, "") for c in cols})

def mark(st, emails, field):
    ts = datetime.now().strftime("%Y-%m-%d")
    for e in emails:
        e = norm(e); st.setdefault(e, {"email": e})
        st[e][field] = ts
    save_status(st)
    print(f"{field}: {len(emails)} marked")

def load_ours():
    ours = {}
    for p in glob.glob(os.path.join(BASE, "**", "*instantly upload*.csv"), recursive=True):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            ours[norm(r["email"])] = r
    return ours

def parse_ts(s):
    s = (s or "").strip()
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
            try: return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except Exception: pass
    return None

def build(exports, cap, sept):
    ours, st = load_ours(), load_status()
    now = datetime.now(timezone.utc)
    rows = []
    for p in exports:
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            e = norm(r.get("Email") or r.get("email"))
            if not e: continue
            last = parse_ts(r.get("timestamp_last_contact") or r.get("Last Contacted") or "")
            opens = int(r.get("email_open_count") or 0); clicks = int(r.get("email_click_count") or 0)
            replied = (r.get("email_replied") or "").lower() in ("true", "1", "yes") or int(r.get("email_reply_count") or 0) > 0
            status = (r.get("Lead Status") or r.get("status") or "")
            if "bounce" in status.lower() or "unsubscribed" in status.lower(): continue
            o = ours.get(e, {})
            rows.append(dict(email=e, first=r.get("First Name") or o.get("first_name", ""), lastname=r.get("Last Name") or o.get("last_name", ""),
                             company=o.get("company_name") or r.get("companyName", ""), title=o.get("title") or r.get("jobTitle", ""),
                             linkedin=o.get("linkedin") or r.get("linkedIn", ""), scorecard=o.get("scorecard_url") or r.get("scorecard_url", ""),
                             total=o.get("ors_total") or r.get("ors_total", ""), opener=o.get("custom_opener") or r.get("custom_opener", ""),
                             last=last, opens=opens, clicks=clicks, replied=replied, completed="completed" in status.lower()))
    connect, message, missing = [], [], 0
    for r in rows:
        s = st.get(r["email"], {})
        if s.get("skipped") or s.get("messaged") or r["replied"]: continue
        if not r["linkedin"]: missing += 1; continue
        if s.get("accepted"):
            dm = (DM_SEPT if sept else DM_NEW).format(first=r["first"], company=r["company"], total=r["total"])
            message.append({**r, "dm": dm}); continue
        if s.get("requested"): continue
        blocked = s.get("followed") or s.get("closed")
        if blocked:
            try: since = datetime.strptime(blocked, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception: since = now
            if (now - since) < timedelta(days=14): continue
            r = {**r, "recheck": "followed on " + blocked if s.get("followed") else "closed on " + blocked}
        # eligible once email 1 has had a day to land: last touch >= 1 day ago, or the sequence is
        # already past step 1 (Completed) or they opened anything
        if r["last"] and ((now - r["last"]) >= timedelta(days=1) or r["completed"] or r["opens"] > 0):
            connect.append(r)
    connect.sort(key=lambda r: (-(r["clicks"] * 10 + r["opens"]), r["last"] or now))
    connect = connect[:cap]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "email", "first", "last", "company", "title", "linkedin", "opens", "clicks", "ors_total", "scorecard_url", "what the email said", "dm_to_paste", "recheck"])
        for r in connect:
            w.writerow(["CONNECT", r["email"], r["first"], r["lastname"], r["company"], r["title"], r["linkedin"], r["opens"], r["clicks"], r["total"], r["scorecard"], r["opener"], "", r.get("recheck", "")])
        for r in message:
            w.writerow(["MESSAGE", r["email"], r["first"], r["lastname"], r["company"], r["title"], r["linkedin"], r["opens"], r["clicks"], r["total"], r["scorecard"], r["opener"], r["dm"], ""])
    fol = sum(1 for v in st.values() if v.get("followed") and not v.get("accepted")); clo = sum(1 for v in st.values() if v.get("closed"))
    req = sum(1 for v in st.values() if v.get("requested") and not v.get("accepted"))
    acc = sum(1 for v in st.values() if v.get("accepted"))
    print(f"CONNECT {len(connect)} (cap {cap})  MESSAGE {len(message)}  no linkedin url: {missing}")
    print(f"so far: requested {req} pending, accepted {acc}, followed {fol}, closed {clo}\n-> {OUT}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="append", default=[], help="Instantly lead export CSV (repeatable)")
    ap.add_argument("--cap", type=int, default=20)
    ap.add_argument("--sept", action="store_true", help="use the September engaged-leads DM text")
    for f in ("requested", "accepted", "messaged", "skip", "follow", "closed"):
        ap.add_argument(f"--{f}", nargs="*", default=None)
    a = ap.parse_args()
    st = load_status(); did = False
    for f, field in (("requested", "requested"), ("accepted", "accepted"), ("messaged", "messaged"), ("skip", "skipped"), ("follow", "followed"), ("closed", "closed")):
        v = getattr(a, f)
        if v: mark(st, v, field); did = True
    if a.export: build(a.export, a.cap, a.sept)
    elif not did: ap.print_help()
