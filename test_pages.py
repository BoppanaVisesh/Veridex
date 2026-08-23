"""Smoke-test all 7 nav pages via their backend endpoints."""
import requests, json

BASE = "http://localhost:8000/api"

results = {}

def check(label, method, path, body=None):
    try:
        if method == "GET":
            r = requests.get(BASE + path, timeout=10)
        else:
            r = requests.post(BASE + path, json=body or {}, timeout=10)
        ok = r.status_code < 400
        try:
            data = r.json()
        except Exception:
            data = r.text[:200]
        results[label] = {"status": r.status_code, "ok": ok, "data": data}
        mark = "[PASS]" if ok else "[FAIL]"
        print(f"{mark} {label} -> HTTP {r.status_code}")
        return data
    except Exception as e:
        results[label] = {"status": "ERR", "ok": False, "error": str(e)}
        print(f"[ERR ] {label} -> {e}")
        return None

print("=" * 60)
print("PAGE 01 — Command Center")
print("=" * 60)
health = check("health", "GET", "/health")
decisions = check("decisions list", "GET", "/decisions")
agents = check("agents list", "GET", "/agents")
metrics = check("platform metrics", "GET", "/metrics")

print()
print("=" * 60)
print("PAGE 02 — Run Scenario")
print("=" * 60)
scenarios = check("scenarios list", "GET", "/scenarios")
# Check catalog products (used by scenario product picker)
cat_prods = check("catalog products", "GET", "/catalog/products")

print()
print("=" * 60)
print("PAGE 03 — Mission Control")
print("=" * 60)
# Mission control needs a decision to show pipeline
if decisions and len(decisions) > 0:
    did = decisions[0].get("decision_id", "")
    if did:
        check(f"decision detail [{did[:12]}]", "GET", f"/decisions/{did}")
else:
    print("  [SKIP] No decisions in DB yet — run a scenario first")

print()
print("=" * 60)
print("PAGE 04 — Investigation")
print("=" * 60)
if decisions and len(decisions) > 0:
    did = decisions[0].get("decision_id", "")
    if did:
        check(f"decision evidence [{did[:12]}]", "GET", f"/decisions/{did}/evidence")
        check(f"decision precedents [{did[:12]}]", "GET", f"/decisions/{did}/precedents")
else:
    print("  [SKIP] No decisions in DB yet")

print()
print("=" * 60)
print("PAGE 05 — Human Review")
print("=" * 60)
if decisions and len(decisions) > 0:
    d = decisions[0]
    did = d.get("decision_id", "")
    check(f"decision for review [{did[:12]}]", "GET", f"/decisions/{did}")
else:
    print("  [SKIP] No decisions in DB yet")

print()
print("=" * 60)
print("PAGE 06 — Platform Metrics")
print("=" * 60)
check("metrics detail", "GET", "/metrics")
check("bidders list", "GET", "/bidders")
check("weights list", "GET", "/weights")

print()
print("=" * 60)
print("PAGE 07 — Catalog Intelligence")
print("=" * 60)
check("catalog health", "GET", "/catalog/health")
check("catalog dashboard", "GET", "/catalog/dashboard")
check("catalog enrichment-mode", "GET", "/catalog/enrichment-mode")
check("catalog pipeline-check", "POST", "/catalog/pipeline-check")
check("catalog products list", "GET", "/catalog/products")

print()
print("=" * 60)
print("PAGE 08 — Unilog Intelligence")
print("=" * 60)
check("unilog preview", "GET", "/catalog/unilog-preview?limit=3")
check("unilog sample export (xlsx)", "GET", "/catalog/unilog-sample-export?limit=5&fmt=xlsx")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for v in results.values() if v["ok"])
failed = [k for k, v in results.items() if not v["ok"]]
print(f"Passed: {passed}/{len(results)}")
if failed:
    print("FAILED:")
    for f in failed:
        v = results[f]
        print(f"  - {f}: HTTP {v.get('status')} | {str(v.get('error',''))[:120]}")
else:
    print("All endpoints OK!")
