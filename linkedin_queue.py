#!/usr/bin/env python3
"""
linkedin_queue.py — today's LinkedIn touches, from an Instantly lead export. No automation.

Reads:  one or more Instantly lead exports (the CSV you get from Campaign > Leads > Export),
        every "HEDWIG campaign 1*instantly upload.csv" in the icp folder (for linkedin url,
        opener, scorecard_url, ors_total), and linkedin-status.csv (what you have already done).
Writes: "LinkedIn today.csv" in the icp folder with two sections:
        CONNECT  (max 20): email 1 sent at least 1 day ago, no request yet. Opens and clicks first.
        MESSAGE  : request accepted, not yet messaged, with the DM text ready to paste.

Mark what you did:
  python3 linkedin_queue.py --requested a@x.com b@y.com
  python3 linkedin_queue.py --accepted a@x.com
  python3 linkedin_queue.py --messaged a@x.com
  python3 linkedin_queue.py --skip a@x.com
Then rebuild the queue:
  python3 linkedin_queue.py --export ~/Downloads/leads.csv [--export another.csv] [--cap 20]
"""
import argparse, csv, glob, os, sys
from datetime import datetime, timezone, timedelta

ICP = os.path.expanduser("~/Claude/Hedwig & Co/icp")
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
    cols = ["email", "requested", "accepted", "messaged", "skipped", "note"]
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
    for p in glob.glob(os.path.join(ICP, "HEDWIG campaign 1*instantly upload.csv")):
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
            o = ours.get(e, {})
            rows.append(dict(email=e, first=r.get("First Name") or o.get("first_name", ""), lastname=r.get("Last Name") or o.get("last_name", ""),
                             company=o.get("company_name") or r.get("companyName", ""), title=o.get("title") or r.get("jobTitle", ""),
                             linkedin=o.get("linkedin") or r.get("linkedIn", ""), scorecard=o.get("scorecard_url") or r.get("scorecard_url", ""),
                             total=o.get("ors_total") or r.get("ors_total", ""), opener=o.get("custom_opener", ""),
                             last=last, opens=opens, clicks=clicks, replied=replied))
    connect, message, missing = [], [], 0
    for r in rows:
        s = st.get(r["email"], {})
        if s.get("skipped") or s.get("messaged") or r["replied"]: continue
        if not r["linkedin"]: missing += 1; continue
        if s.get("accepted"):
            dm = (DM_SEPT if sept else DM_NEW).format(first=r["first"], company=r["company"], total=r["total"])
            message.append({**r, "dm": dm}); continue
        if s.get("requested"): continue
        if r["last"] and (now - r["last"]) >= timedelta(days=1):
            connect.append(r)
    connect.sort(key=lambda r: (-(r["clicks"] * 10 + r["opens"]), r["last"] or now))
    connect = connect[:cap]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "email", "first", "last", "company", "title", "linkedin", "opens", "clicks", "ors_total", "scorecard_url", "what the email said", "dm_to_paste"])
        for r in connect:
            w.writerow(["CONNECT", r["email"], r["first"], r["lastname"], r["company"], r["title"], r["linkedin"], r["opens"], r["clicks"], r["total"], r["scorecard"], r["opener"], ""])
        for r in message:
            w.writerow(["MESSAGE", r["email"], r["first"], r["lastname"], r["company"], r["title"], r["linkedin"], r["opens"], r["clicks"], r["total"], r["scorecard"], r["opener"], r["dm"]])
    print(f"CONNECT {len(connect)} (cap {cap})  MESSAGE {len(message)}  no linkedin url: {missing}\n-> {OUT}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="append", default=[], help="Instantly lead export CSV (repeatable)")
    ap.add_argument("--cap", type=int, default=20)
    ap.add_argument("--sept", action="store_true", help="use the September engaged-leads DM text")
    for f in ("requested", "accepted", "messaged", "skip"):
        ap.add_argument(f"--{f}", nargs="*", default=None)
    a = ap.parse_args()
    st = load_status(); did = False
    for f, field in (("requested", "requested"), ("accepted", "accepted"), ("messaged", "messaged"), ("skip", "skipped")):
        v = getattr(a, f)
        if v: mark(st, v, field); did = True
    if a.export: build(a.export, a.cap, a.sept)
    elif not did: ap.print_help()
