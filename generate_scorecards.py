#!/usr/bin/env python3
"""
generate_scorecards.py — run the Outbound Readiness Score for every company in a lead CSV.

Calls the deployed tools app (no browser, no local API keys). Logs in with the tools
portal password, posts each unique domain to /api/scorecard, retries on network errors,
and writes scorecards-<date>.csv with slug, total and the hedwigandco.com page URL.

  python3 generate_scorecards.py --password PORTAL_PASSWORD
  python3 generate_scorecards.py --password ... --csv "path/to/leads.csv" --force
"""
import argparse, csv, json, sys, time, urllib.request, urllib.error, http.cookiejar
from urllib.parse import urlencode

DEFAULT_CSV = "/Users/fareehafatima/Claude/Hedwig & Co/icp/HEDWIG campaign 1 - first 100.csv"
BASE = "https://tools.fareehafatima.com"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", required=True)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--force", action="store_true", help="regenerate even if a page exists")
    ap.add_argument("--only", default="", help="comma-separated domains to run")
    a = ap.parse_args()

    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    # login
    r = op.open(urllib.request.Request(BASE + "/login", data=urlencode({"password": a.password}).encode(),
                                       headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=30)
    if not any(c for c in cj):
        print("login failed (no session cookie). Check the password."); sys.exit(1)

    companies = {}
    with open(a.csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("domain") or "").strip().lower()
            if d and d not in companies:
                companies[d] = (row.get("company") or d).strip()
    if a.only:
        keep = {x.strip().lower() for x in a.only.split(",")}
        companies = {d: c for d, c in companies.items() if d in keep}

    out_path = f"scorecards-{time.strftime('%Y-%m-%d')}.csv"
    done = {}
    print(f"{len(companies)} companies -> {out_path}")
    with open(out_path, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo); w.writerow(["domain", "company", "slug", "total", "band", "page_url", "status"])
        for i, (d, c) in enumerate(companies.items(), 1):
            res = None
            for attempt in range(1, 5):
                try:
                    body = json.dumps({"domain": d, "company": c, "force": a.force}).encode()
                    req = urllib.request.Request(BASE + "/api/scorecard", data=body, method="POST",
                                                 headers={"Content-Type": "application/json"})
                    with op.open(req, timeout=180) as resp:
                        res = json.loads(resp.read().decode("utf-8", "ignore"))
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                    print(f"  [{i}/{len(companies)}] {d}: network error ({e}), retry {attempt}/4"); time.sleep(15)
                except urllib.error.HTTPError as e:
                    res = {"error": f"HTTP {e.code}: {e.read().decode('utf-8','ignore')[:200]}"}; break
            if not res:
                w.writerow([d, c, "", "", "", "", "failed after retries"]); fo.flush(); continue
            if res.get("error"):
                print(f"  [{i}/{len(companies)}] {d}: ERROR {res['error'][:120]}")
                w.writerow([d, c, "", "", "", "", res["error"][:200]]); fo.flush(); continue
            rv = res.get("review") or {}
            cached = "cached" if res.get("cached") else "generated"
            print(f"  [{i}/{len(companies)}] {d}: {rv.get('total')}/50 {rv.get('band','')} ({cached})  {res.get('page_url')}")
            w.writerow([d, c, res.get("slug"), rv.get("total"), rv.get("band"), res.get("page_url"), cached]); fo.flush()
            done[d] = rv.get("total")
    print(f"\n{len(done)} pages. Results in {out_path}")

if __name__ == "__main__":
    main()
