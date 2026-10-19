"""
Scout, the lead builder agent.
Search is free (Apollo people api_search). Verify is paid (bulk_match, 1 credit per person),
capped per run and only when APOLLO_ENRICH=1, same guard as the kit.
"""
import os, json, csv, io, datetime
from apollo import Apollo

SIZE_RANGES = {
    "11-50": "11,50", "51-200": "51,200", "201-500": "201,500", "501-1000": "501,1000",
}
SIGNALS = {
    "hiring_sales": {"q_organization_job_titles": ["sales", "business development", "account executive", "growth", "marketing"]},
    "hiring_clinical": {"q_organization_job_titles": ["clinical", "medical director", "nurse", "physician"]},
    "funded": {"latest_funding_date_days": 365},
}
MAX_PAGES = 5           # 5 x 100 = 500 people per run
VERIFY_CAP = 8          # credits per verify call, same cap as the kit

def _days_ago(n):
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()

def build_body(q, page=1, per_page=100):
    body = {"page": page, "per_page": per_page, "contact_email_status": ["verified"]}
    if q.get("titles"):      body["person_titles"] = q["titles"]
    if q.get("sizes"):       body["organization_num_employees_ranges"] = [SIZE_RANGES.get(s, s) for s in q["sizes"]]
    if q.get("keywords"):    body["q_organization_keyword_tags"] = q["keywords"]
    if q.get("locations"):   body["organization_locations"] = q["locations"]
    if q.get("person_locations"): body["person_locations"] = q["person_locations"]
    if q.get("seniorities"): body["person_seniorities"] = q["seniorities"]
    sig = q.get("signal")
    if sig in ("hiring_sales", "hiring_clinical"):
        body.update(SIGNALS[sig]); body["organization_job_posted_at_range"] = {"min": _days_ago(90), "max": datetime.date.today().isoformat()}
    elif sig == "funded":
        body["latest_funding_date_range"] = {"min": _days_ago(365), "max": datetime.date.today().isoformat()}
    return body

def _row(p):
    org = p.get("organization") or {}
    return {
        "id": p.get("id"),
        "first_name": p.get("first_name") or "",
        "last_name": p.get("last_name") or "",
        "title": p.get("title") or "",
        "company": org.get("name") or "",
        "domain": org.get("primary_domain") or "",
        "employees": org.get("estimated_num_employees"),
        "city": p.get("city") or "", "state": p.get("state") or "", "country": p.get("country") or "",
        "linkedin": p.get("linkedin_url") or "",
        "email": p.get("email") or "",
        "email_status": p.get("email_status") or "",
        "verified": False,
    }

def search(q, max_pages=MAX_PAGES, exclude_domains=None):
    a = Apollo()
    exclude = {d.strip().lower() for d in (exclude_domains or []) if d.strip()}
    people, total, seen = [], None, set()
    for page in range(1, max_pages + 1):
        r = a._post("/mixed_people/api_search", build_body(q, page=page))
        if r.get("_error"):
            return {"error": r["_error"], "people": people, "total": total}
        if total is None:
            total = (r.get("pagination") or {}).get("total_entries")
        batch = r.get("people") or []
        for p in batch:
            row = _row(p)
            if not row["id"] or row["id"] in seen: continue
            if row["domain"].lower() in exclude: continue
            seen.add(row["id"]); people.append(row)
        if len(batch) < 100: break
        if q.get("limit") and len(people) >= q["limit"]: break
    if q.get("limit"): people = people[: q["limit"]]
    companies = len({p["domain"] or p["company"] for p in people})
    return {"total": total, "returned": len(people), "companies": companies, "people": people}

def verify(ids):
    if os.environ.get("APOLLO_ENRICH", "") != "1":
        return {"error": "APOLLO_ENRICH is not set to 1, verify is off", "people": []}
    ids = [i for i in ids if i][:VERIFY_CAP]
    out = Apollo().enrich_people(ids)
    return {"people": out, "used": len(out)}

INSTANTLY_COLS = ["email", "first_name", "last_name", "company_name", "website", "title", "linkedin", "city", "state", "country", "employees"]

def to_csv(people):
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=INSTANTLY_COLS); w.writeheader()
    for p in people:
        w.writerow({"email": p.get("email", ""), "first_name": p.get("first_name", ""), "last_name": p.get("last_name", ""),
                    "company_name": p.get("company", ""), "website": p.get("domain", ""), "title": p.get("title", ""),
                    "linkedin": p.get("linkedin", ""), "city": p.get("city", ""), "state": p.get("state", ""),
                    "country": p.get("country", ""), "employees": p.get("employees", "")})
    return buf.getvalue()
