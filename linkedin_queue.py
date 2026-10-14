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


# ---------------------------------------------------------------- dashboard

DASH = os.path.join(ICP, "Leads dashboard.html")

def dashboard(exports):
    import json, html
    ours, st = load_ours(), load_status()
    leads = []
    for p in exports:
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            e = norm(r.get("Email") or r.get("email"))
            if not e: continue
            o = ours.get(e, {}); s = st.get(e, {})
            camp = r.get("Campaign Name") or r.get("campaign") or os.path.basename(p)
            status = r.get("Lead Status") or ""
            opened = r.get("email_opened") or ""; clicked = r.get("email_clicked") or ""
            steps_opened = [i + 1 for i, v in enumerate(opened.split("_")) if v.isdigit() and int(v) > 0] if opened else []
            steps_clicked = [i + 1 for i, v in enumerate(clicked.split("_")) if v.isdigit() and int(v) > 0] if clicked else []
            if "bounce" in status.lower(): seq = "bounced"
            elif status.lower().startswith("completed"): seq = "all 3 sent"
            elif status.lower().startswith("active"): seq = "in sequence"
            else: seq = status or "?"
            li = "messaged" if s.get("messaged") else "accepted" if s.get("accepted") else "requested" if s.get("requested") else "closed" if s.get("closed") else "follow only" if s.get("followed") else ""
            leads.append(dict(email=e, name=f'{r.get("First Name","")} {r.get("Last Name","")}'.strip(), company=o.get("company_name") or r.get("companyName",""),
                title=o.get("title") or r.get("jobTitle",""), campaign=camp, channel="multi-channel" if li else "email only",
                seq=seq, status=status, opens=int(r.get("email_open_count") or 0), clicks=int(r.get("email_click_count") or 0),
                steps_opened=steps_opened, steps_clicked=steps_clicked, replied=int(r.get("email_reply_count") or 0) > 0,
                interest=r.get("Interest Status",""), last=(r.get("timestamp_last_contact") or "")[:10], sender=r.get("Last contacted from",""),
                li=li, li_date=s.get("messaged") or s.get("accepted") or s.get("requested") or s.get("followed") or s.get("closed") or "",
                linkedin=o.get("linkedin") or r.get("linkedIn",""), score=o.get("ors_total") or r.get("ors_total",""), page=o.get("scorecard_url") or r.get("scorecard_url","")))
    data = json.dumps(leads)
    page = """<!doctype html><meta charset=utf-8><title>HEDWIG leads</title>
<style>
body{font-family:-apple-system,Inter,system-ui,sans-serif;background:#fbf9f5;color:#1a1a1a;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}.sub{color:#666;font-size:13px;margin-bottom:18px}
.tiles{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}.tile{background:#fff;border:1px solid #e8e2d6;border-radius:10px;padding:12px 16px;min-width:120px}
.tile b{display:block;font-size:24px}.tile span{font-size:12px;color:#666}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
.bar button{border:1px solid #d8d0c2;background:#fff;border-radius:999px;padding:6px 12px;font-size:13px;cursor:pointer}
.bar button.on{background:#1f3a5f;color:#fff;border-color:#1f3a5f}.bar input{padding:6px 10px;border:1px solid #d8d0c2;border-radius:8px;font-size:13px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e8e2d6;border-radius:10px;overflow:hidden;font-size:13px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #f0ebe2;vertical-align:top}th{background:#f4efe6;font-weight:600;cursor:pointer;white-space:nowrap}
tr.click td{background:#fff7f4}tr.reply td{background:#eef6ee}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;background:#eee}.pill.mc{background:#1f3a5f;color:#fff}.pill.li{background:#b5422a;color:#fff}.pill.seq{background:#e6e0d4}
a{color:#1f3a5f}.muted{color:#999}
</style>
<h1>HEDWIG leads</h1><div class=sub id=sub></div>
<div class=tiles id=tiles></div>
<div class=bar>
 <b style="font-size:12px">Channel</b><button data-f=channel data-v="">All</button><button data-f=channel data-v="multi-channel">Multi-channel</button><button data-f=channel data-v="email only">Email only</button>
 <b style="font-size:12px;margin-left:10px">Campaign</b><span id=camps></span>
 <b style="font-size:12px;margin-left:10px">Show</b><button data-f=special data-v="">All</button><button data-f=special data-v=clicked>Clicked</button><button data-f=special data-v=opened>Opened</button><button data-f=special data-v=untouched>No open</button><button data-f=special data-v=bounced>Bounced</button>
 <input id=q placeholder="search name / company" style="margin-left:auto">
</div>
<table><thead><tr><th data-k=name>Name</th><th data-k=company>Company</th><th data-k=campaign>Campaign</th><th data-k=channel>Channel</th><th data-k=seq>Email sequence</th><th>Opened steps</th><th data-k=clicks>Clicks</th><th data-k=last>Last email</th><th data-k=li>LinkedIn</th><th data-k=score>ORS</th></tr></thead><tbody id=tb></tbody></table>
<script>
const L=__DATA__;const F={channel:"",campaign:"",special:""};let sortK="clicks",sortD=-1;
const camps=[...new Set(L.map(x=>x.campaign))];document.getElementById("camps").innerHTML='<button data-f=campaign data-v="" class=on>All</button>'+camps.map(c=>`<button data-f=campaign data-v="${c}">${c}</button>`).join("");
document.querySelectorAll(".bar button").forEach(b=>b.onclick=()=>{F[b.dataset.f]=b.dataset.v;document.querySelectorAll(`.bar button[data-f=${b.dataset.f}]`).forEach(x=>x.classList.toggle("on",x===b));render()});
document.querySelectorAll(".bar button[data-v='']").forEach(b=>b.classList.add("on"));
document.querySelectorAll("th[data-k]").forEach(h=>h.onclick=()=>{if(sortK===h.dataset.k)sortD*=-1;else{sortK=h.dataset.k;sortD=h.dataset.k==="clicks"||h.dataset.k==="score"?-1:1}render()});
document.getElementById("q").oninput=render;
function rows(){const q=document.getElementById("q").value.toLowerCase();return L.filter(x=>(!F.channel||x.channel===F.channel)&&(!F.campaign||x.campaign===F.campaign)&&(!F.special||(F.special==="clicked"?x.clicks>0:F.special==="opened"?x.opens>0:F.special==="untouched"?x.opens===0&&x.seq!=="bounced":x.seq==="bounced"))&&(!q||(x.name+" "+x.company).toLowerCase().includes(q)))}
function render(){const R=rows();R.sort((a,b)=>{let va=a[sortK],vb=b[sortK];if(typeof va==="string")return va.localeCompare(vb)*sortD;return (va-vb)*sortD||b.opens-a.opens});
const t=document.getElementById("tb");t.innerHTML=R.map(x=>`<tr class="${x.replied?"reply":x.clicks?"click":""}"><td><a href="${x.linkedin}" target=_blank>${x.name}</a><div class=muted>${x.title}</div></td><td>${x.company}</td><td>${x.campaign}</td><td><span class="pill ${x.channel==="multi-channel"?"mc":""}">${x.channel}</span></td><td><span class="pill seq">${x.seq}</span>${x.interest&&x.interest!=="Lead"?"<div class=muted>"+x.interest+"</div>":""}</td><td>${x.steps_opened.length?x.steps_opened.map(s=>"step "+s).join(", "):"<span class=muted>none</span>"}${x.steps_clicked.length?"<div>clicked "+x.steps_clicked.map(s=>"step "+s).join(", ")+"</div>":""}</td><td>${x.clicks}</td><td>${x.last}<div class=muted>${x.sender}</div></td><td>${x.li?`<span class="pill li">${x.li}</span><div class=muted>${x.li_date}</div>`:"<span class=muted>not yet</span>"}</td><td>${x.page?`<a href="${x.page}" target=_blank>${x.score}</a>`:x.score}</td></tr>`).join("");
const all=L.length,sent=L.filter(x=>x.seq!=="bounced").length,op=L.filter(x=>x.opens>0).length,cl=L.filter(x=>x.clicks>0).length,bo=L.filter(x=>x.seq==="bounced").length,req=L.filter(x=>x.li==="requested").length,acc=L.filter(x=>x.li==="accepted"||x.li==="messaged").length,mc=L.filter(x=>x.channel==="multi-channel").length;
document.getElementById("tiles").innerHTML=[["Leads",all],["Delivered",sent],["Opened",op+" ("+Math.round(100*op/sent)+"%)"],["Clicked score page",cl+" ("+Math.round(100*cl/sent)+"%)"],["Bounced",bo],["Multi-channel",mc],["LinkedIn requested",req],["LinkedIn accepted",acc]].map(([k,v])=>`<div class=tile><b>${v}</b><span>${k}</span></div>`).join("");
document.getElementById("sub").textContent=`${R.length} shown. Generated ${new Date().toLocaleString()}. Click a column to sort.`}
render();
</script>""".replace("__DATA__", data)
    open(DASH, "w", encoding="utf-8").write(page)
    print(f"dashboard: {len(leads)} leads -> {DASH}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="append", default=[], help="Instantly lead export CSV (repeatable)")
    ap.add_argument("--cap", type=int, default=20)
    ap.add_argument("--sept", action="store_true", help="use the September engaged-leads DM text")
    ap.add_argument("--dashboard", action="store_true", help="also write LEADS/Leads dashboard.html")
    for f in ("requested", "accepted", "messaged", "skip", "follow", "closed"):
        ap.add_argument(f"--{f}", nargs="*", default=None)
    a = ap.parse_args()
    st = load_status(); did = False
    for f, field in (("requested", "requested"), ("accepted", "accepted"), ("messaged", "messaged"), ("skip", "skipped"), ("follow", "followed"), ("closed", "closed")):
        v = getattr(a, f)
        if v: mark(st, v, field); did = True
    if a.export:
        build(a.export, a.cap, a.sept)
        if a.dashboard: dashboard(a.export)
    elif not did: ap.print_help()
