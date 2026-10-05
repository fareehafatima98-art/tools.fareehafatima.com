"""
leads.py — lead management system (multi-client).

One JSON document per client at Blob path leads/<client>.json:
{
  "client": "hedwig", "name": "HEDWIG", "updated": iso,
  "leads": { "<email>": {...lead...} },
  "tests": { "<test_id>": {...test...} }
}

Lead fields (all optional except email):
  email first last company domain title city country tz segment signal campaign inbox
  status stage last_sent last_event reply_count last_reply_text our_last_reply_text
  next_action next_due notes asset_url source test_variant
Status: not-contacted contacted opened clicked replied warm hot call-booked won lost do-not-contact
Stage:  step1 step2 step3 in-conversation handed-off closed

Manual fields are never overwritten by a sync: status (if warm/hot/do-not-contact/won/lost),
stage (if in-conversation/handed-off/closed), next_action, next_due, notes, our_last_reply_text,
test_variant, segment, signal.
"""
import os, io, csv, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import storage

STATUSES = ["not-contacted","contacted","opened","clicked","replied","warm","hot","call-booked","won","lost","do-not-contact"]
STAGES   = ["step1","step2","step3","in-conversation","handed-off","closed"]
MANUAL_STATUS = {"warm","hot","do-not-contact","won","lost","call-booked"}
MANUAL_STAGE  = {"in-conversation","handed-off","closed"}
MANUAL_FIELDS = {"next_action","next_due","notes","our_last_reply_text","test_variant","segment","signal"}
STATUS_RANK = {s:i for i,s in enumerate(STATUSES)}

def _now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def _norm(e): return (e or "").strip().lower()
def _path(client): return f"leads/{re.sub(r'[^a-z0-9-]','-',client.lower())}.json"

# ---------------------------------------------------------------- load / save

def load(client: str) -> Dict[str, Any]:
    doc = storage.fetch_json(_path(client))
    if not doc:
        doc = {"client": client, "name": client.upper(), "updated": _now(), "leads": {}, "tests": {}}
    doc.setdefault("leads", {}); doc.setdefault("tests", {})
    return doc

def save(client: str, doc: Dict[str, Any]) -> bool:
    doc["updated"] = _now()
    return storage.save_json(_path(client), doc)

def list_clients() -> List[str]:
    idx = storage.fetch_json("leads/_clients.json") or {"clients": ["hedwig"]}
    return idx.get("clients", ["hedwig"])

def add_client(client: str, name: str = ""):
    idx = storage.fetch_json("leads/_clients.json") or {"clients": ["hedwig"]}
    c = re.sub(r'[^a-z0-9-]','-',client.lower())
    if c not in idx["clients"]:
        idx["clients"].append(c); storage.save_json("leads/_clients.json", idx)
    doc = load(c)
    if name: doc["name"] = name
    save(c, doc)
    return c

# ---------------------------------------------------------------- upsert with manual-field protection

def upsert(doc: Dict[str, Any], rec: Dict[str, Any], from_sync: bool = False) -> Dict[str, Any]:
    email = _norm(rec.get("email"))
    if not email: return None
    cur = doc["leads"].get(email) or {"email": email, "status": "not-contacted", "stage": "step1",
                                      "reply_count": 0, "created": _now(), "source": rec.get("source","manual")}
    for k, v in rec.items():
        if v in (None, ""): continue
        if from_sync:
            if k in MANUAL_FIELDS and cur.get(k): continue
            if k == "status" and cur.get("status") in MANUAL_STATUS: continue
            if k == "stage"  and cur.get("stage")  in MANUAL_STAGE:  continue
            # sync may only move status forward, never backward
            if k == "status" and STATUS_RANK.get(v, -1) < STATUS_RANK.get(cur.get("status"), -1): continue
        cur[k] = v
    cur["email"] = email
    cur["updated"] = _now()
    doc["leads"][email] = cur
    return cur

# ---------------------------------------------------------------- CSV import

_COLMAP = {
    "email":"email","email address":"email","recipient email":"email",
    "first name":"first","first_name":"first","firstname":"first",
    "last name":"last","last_name":"last","lastname":"last",
    "company":"company","company name":"company","organization":"company",
    "domain":"domain","website":"domain","title":"title","job title":"title",
    "city":"city","country":"country","timezone":"tz","timezone calculated":"tz",
    "segment":"segment","signal":"signal","campaign":"campaign","inbox":"inbox","sender email":"inbox",
    "status":"status","stage":"stage","notes":"notes","next action":"next_action","next due":"next_due",
    "review url":"asset_url","review_url":"asset_url","asset_url":"asset_url","test_variant":"test_variant","variant":"test_variant",
}

def import_csv(doc: Dict[str, Any], text: str, campaign: str = "", source: str = "csv") -> Dict[str, int]:
    """Generic lead CSV or an Instantly Activity export. Returns counts."""
    rdr = csv.DictReader(io.StringIO(text))
    n_new = n_upd = 0
    headers = [h.strip().lower() for h in (rdr.fieldnames or [])]
    is_activity = "action" in headers and "recipient email" in headers
    for row in rdr:
        r = {}
        for k, v in row.items():
            if k is None: continue
            kk = _COLMAP.get(k.strip().lower())
            if kk: r[kk] = (v or "").strip()
        if not r.get("email"): continue
        if campaign and not r.get("campaign"): r["campaign"] = campaign
        r["source"] = source
        if is_activity:
            act = (row.get("Action") or row.get("action") or "").strip().lower()
            ts = (row.get("Date") or row.get("date") or "").strip()
            if act == "email sent":        r["status"] = "contacted"; r["last_sent"] = ts
            elif act == "email opened":    r["status"] = "opened";    r["last_event"] = ts
            elif act == "link clicked":    r["status"] = "clicked";   r["last_event"] = ts
            elif act == "reply received":  r["status"] = "replied";   r["last_event"] = ts
            step = (row.get("Step") or row.get("step") or "").strip().lower().replace(" ","")
            if step in STAGES: r["stage"] = step
            existed = r["email"].lower() in doc["leads"]
            lead = upsert(doc, r, from_sync=True)
            if lead and act == "reply received":
                lead["reply_count"] = int(lead.get("reply_count") or 0) + 1
        else:
            existed = r["email"].lower() in doc["leads"]
            upsert(doc, r, from_sync=False)
        if existed: n_upd += 1
        else: n_new += 1
    return {"new": n_new, "updated": n_upd}

# ---------------------------------------------------------------- Instantly API v2 sync (best effort)

def _inst(path, key, method="GET", body=None, params=None):
    base = "https://api.instantly.ai/api/v2"
    url = base + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8","ignore"))

def sync_instantly(doc: Dict[str, Any], api_key: str, campaign_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Pull leads + emails from Instantly v2. Returns a report. Never raises on API errors."""
    report = {"campaigns": 0, "leads": 0, "emails": 0, "errors": []}
    try:
        camps = _inst("/campaigns", api_key, params={"limit": 100}).get("items", [])
    except Exception as e:
        report["errors"].append(f"campaigns: {e}"); return report
    for c in camps:
        cid, cname = c.get("id"), c.get("name","")
        if campaign_ids and cid not in campaign_ids: continue
        report["campaigns"] += 1
        # leads
        try:
            cursor = None
            while True:
                body = {"campaign": cid, "limit": 100}
                if cursor: body["starting_after"] = cursor
                page = _inst("/leads/list", api_key, method="POST", body=body)
                items = page.get("items", [])
                for L in items:
                    st = "contacted" if L.get("email_sent_count") or L.get("timestamp_last_contact") else "not-contacted"
                    if L.get("email_open_count"): st = "opened"
                    if L.get("email_click_count"): st = "clicked"
                    if L.get("email_reply_count"): st = "replied"
                    upsert(doc, {"email": L.get("email"), "first": L.get("first_name"), "last": L.get("last_name"),
                                 "company": L.get("company_name"), "domain": L.get("website"), "title": L.get("job_title") or (L.get("payload") or {}).get("title"),
                                 "campaign": cname, "status": st, "last_sent": L.get("timestamp_last_contact"),
                                 "reply_count": L.get("email_reply_count") or 0, "source": "instantly"}, from_sync=True)
                    report["leads"] += 1
                cursor = page.get("next_starting_after")
                if not cursor or not items: break
        except Exception as e:
            report["errors"].append(f"leads {cname}: {e}")
        # reply bodies
        try:
            page = _inst("/emails", api_key, params={"campaign_id": cid, "limit": 100, "email_type": "received"})
            for E in page.get("items", []):
                em = _norm(E.get("from_address_email") or E.get("lead"))
                if em in doc["leads"]:
                    lead = doc["leads"][em]
                    body = (E.get("body") or {}).get("text") or E.get("body_text") or ""
                    lead["last_reply_text"] = body[:1500]
                    lead["last_event"] = E.get("timestamp_email") or lead.get("last_event")
                    if lead.get("status") not in MANUAL_STATUS: lead["status"] = "replied"
                    report["emails"] += 1
        except Exception as e:
            report["errors"].append(f"emails {cname}: {e}")
    return report

# ---------------------------------------------------------------- tests

def test_stats(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for tid, t in doc["tests"].items():
        variants = {v: {"n":0,"contacted":0,"opened":0,"clicked":0,"replied":0,"positive":0} for v in t.get("variants", [])}
        for L in doc["leads"].values():
            v = L.get("test_variant")
            if v not in variants or L.get("test_id", tid) != tid: continue
            s = variants[v]; s["n"] += 1
            r = STATUS_RANK.get(L.get("status"), 0)
            if r >= STATUS_RANK["contacted"]: s["contacted"] += 1
            if r >= STATUS_RANK["opened"]:    s["opened"] += 1
            if r >= STATUS_RANK["clicked"]:   s["clicked"] += 1
            if r >= STATUS_RANK["replied"]:   s["replied"] += 1
            if L.get("status") in ("warm","hot","call-booked","won"): s["positive"] += 1
        for v, s in variants.items():
            c = s["contacted"] or 1
            s["reply_rate"] = round(100*s["replied"]/c, 1); s["positive_rate"] = round(100*s["positive"]/c, 1); s["click_rate"] = round(100*s["clicked"]/c, 1)
        out[tid] = {**t, "id": tid, "stats": variants}
    return out

# ---------------------------------------------------------------- views

def summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    by_status = {s:0 for s in STATUSES}; by_segment = {}; by_signal = {}
    for L in doc["leads"].values():
        by_status[L.get("status","not-contacted")] = by_status.get(L.get("status","not-contacted"),0) + 1
        seg = L.get("segment") or "unassigned"; by_segment[seg] = by_segment.get(seg,0)+1
        sig = L.get("signal") or "none"; by_signal[sig] = by_signal.get(sig,0)+1
    return {"total": len(doc["leads"]), "by_status": by_status, "by_segment": by_segment, "by_signal": by_signal}

def to_csv(doc: Dict[str, Any]) -> str:
    cols = ["email","first","last","company","domain","title","city","country","tz","segment","signal","campaign","inbox",
            "status","stage","last_sent","last_event","reply_count","last_reply_text","our_last_reply_text",
            "next_action","next_due","notes","asset_url","source","test_id","test_variant","updated"]
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for L in sorted(doc["leads"].values(), key=lambda x: (-STATUS_RANK.get(x.get("status"),0), x.get("company") or "")):
        w.writerow(L)
    return buf.getvalue()
