"""
Targeted audit of all API endpoints used by the 7 nav pages.
Tests exactly what each page's JS calls.
"""
import requests, time

BASE = "http://localhost:8000/api"
PASS, FAIL = [], []

def chk(label, method, path, body=None):
    url = BASE + path
    try:
        r = requests.request(method, url, json=body, timeout=8)
        ok = r.status_code < 400
        status = r.status_code
        try:
            snippet = str(r.json())[:80]
        except Exception:
            snippet = r.text[:80]
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {method:4} {path:50} -> {status}  {snippet}")
        (PASS if ok else FAIL).append(label)
        return r.json() if ok else None
    except Exception as e:
        print(f"  [ERR ] {method:4} {path:50} -> {e}")
        FAIL.append(label)
        return None

# Wait for server
time.sleep(2)
print("=" * 72)
print("PAGE 01 - Command Center")
print("=" * 72)
chk("health",    "GET", "/health")
d = chk("decisions", "GET", "/decisions")
decisions = (d.get("decisions",[]) if isinstance(d,dict) else d) or []
live = [x for x in decisions if not x.get("decision_id","").startswith("HIST-") and x.get("description")]
chk("scenarios", "GET", "/scenarios")

print()
print("=" * 72)
print("PAGE 02 - Run Scenario")
print("=" * 72)
chk("scenarios list",  "GET", "/scenarios")
chk("catalog products","GET", "/catalog/products")

print()
print("=" * 72)
print("PAGES 03/04/05 - Mission Control / Investigation / Human Review")
print("(requires a live decision)")
print("=" * 72)

if not live:
    print("  No live decisions — creating one via D7 scenario...")
    r2 = chk("run D7", "POST", "/decisions/run-scenario", {"decision_type": "D7"})
    if r2 and r2.get("decision_id"):
        live = [r2]

if live:
    did = live[0]["decision_id"]
    print(f"  Using decision: {did}")
    chk("decision detail",   "GET",  f"/decisions/{did}")
    chk("decision progress", "GET",  f"/decisions/{did}/progress")
    chk("trace",             "GET",  f"/trace/{did}")
    chk("why-not",           "POST", f"/decisions/{did}/why-not", {"alternative": "reject"})
    # Wait briefly for pipeline to complete before whatif
    time.sleep(3)
    chk("whatif",            "POST", f"/decisions/{did}/whatif",  {"overrides": {"field_completeness_pct": 90}})
    chk("respond",           "POST", f"/decisions/{did}/respond", {"decision": "accept", "edit_description": ""})
else:
    print("  [SKIP] Could not create decision")

print()
print("=" * 72)
print("PAGE 06 - Platform Metrics")
print("=" * 72)
chk("metrics",            "GET", "/metrics")
chk("metrics/influence",  "GET", "/metrics/influence")
chk("metrics/weights",    "GET", "/metrics/weights")
chk("metrics/calibration","GET", "/metrics/calibration")
chk("evaluate",           "GET", "/evaluate")

print()
print("=" * 72)
print("PAGE 07 - Catalog Intelligence")
print("=" * 72)
chk("catalog/health",           "GET",  "/catalog/health")
chk("catalog/dashboard",        "GET",  "/catalog/dashboard")
chk("catalog/enrichment-mode",  "GET",  "/catalog/enrichment-mode")
chk("catalog/products",         "GET",  "/catalog/products")
chk("catalog/pipeline-check",   "POST", "/catalog/pipeline-check", {})
# clear-demo-data requires confirmed=true — safety guard by design
chk("catalog/clear-demo-data",  "POST", "/catalog/clear-demo-data", {"confirmed": True})

# Get a product ID for detail endpoints
prod = chk("catalog/products (for ID)", "GET", "/catalog/products")
if isinstance(prod, list) and prod:
    pid = prod[0].get("id") or prod[0].get("product_id","")
    if pid:
        chk(f"catalog/products/{pid}", "GET", f"/catalog/products/{pid}")
        chk(f"validate product",       "POST", f"/catalog/products/{pid}/validate", {})
        chk(f"enrich product",         "POST", f"/catalog/products/{pid}/enrich",   {})
        chk(f"explain field",          "GET",  f"/catalog/products/{pid}/explain/name")

print()
print("=" * 72)
print("PAGE 08 - Unilog Intelligence")
print("=" * 72)
chk("unilog-preview",       "GET", "/catalog/unilog-preview?limit=3")
chk("unilog-sample-export csv",  "GET", "/catalog/unilog-sample-export?limit=5&fmt=csv")
chk("unilog-sample-export xlsx", "GET", "/catalog/unilog-sample-export?limit=5&fmt=xlsx")

print()
print("=" * 72)
print(f"SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
print("=" * 72)
if FAIL:
    print("FAILED endpoints:")
    for f in FAIL:
        print(f"  - {f}")
else:
    print("All endpoints healthy!")
