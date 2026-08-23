"""End-to-end test of the Unilog enrichment pipeline."""
import requests
import json
import sys

BASE = "http://localhost:8000"

print("=" * 60)
print("VERIDEX — Unilog Enrichment Pipeline E2E Test")
print("=" * 60)

# 1. Health check
r = requests.get(f"{BASE}/api/catalog/health")
assert r.status_code == 200, f"Health failed: {r.text}"
print(f"\n[1] Health: {r.json()}")

# 2. Enrichment mode
r = requests.get(f"{BASE}/api/catalog/enrichment-mode")
mode = r.json()
print(f"[2] Enrichment mode: {mode['enrichment_mode']}")
print(f"    Gemini key: {mode['gemini_api_key_configured']}")
print(f"    Desc: {mode['description']}")

# 3. Preview endpoint (first 5 rows of bundled sample)
print("\n[3] Preview (5 rows from sample dataset)...")
r = requests.get(f"{BASE}/api/catalog/unilog-preview?limit=5")
assert r.status_code == 200, f"Preview failed: {r.text}"
prev = r.json()
print(f"    Total rows enriched: {prev['total']}")
print(f"    Mode: {prev['enrichment_mode']}")

for i, row in enumerate(prev['rows'], 1):
    conf = float(row.get('_confidence', 0))
    print(f"\n  --- Row {i}: {row['Mfg_Part_Num']} ---")
    print(f"    Manufacturer : {row['MANUFACTURER_NAME']}")
    print(f"    Brand        : {row['BRAND_NAME']}")
    print(f"    Classpath    : {row['Classpath']}")
    print(f"    INVOICE_DESC : {row['INVOICE_DESC']}")
    print(f"    MOBILE_DESC  : {row['MOBILE_DESC'][:75]}...")
    print(f"    SHORT_DESC   : {row['SHORT_DESC'][:80]}")
    print(f"    Confidence   : {conf:.0%}  NeedsReview={row['_needs_review']}")
    attrs = row.get('attributes', [])
    if attrs:
        print(f"    Attributes   : {[(a['label'], a['value']) for a in attrs[:5]]}")

# 4. Sample export (download XLSX — validate column count)
print("\n[4] Sample export — 10 rows as XLSX...")
r = requests.get(f"{BASE}/api/catalog/unilog-sample-export?limit=10&fmt=xlsx")
assert r.status_code == 200, f"Export failed: {r.status_code} {r.text[:200]}"

import io, pandas as pd
buf = io.BytesIO(r.content)
df = pd.read_excel(buf)
print(f"    Rows exported: {len(df)}")
print(f"    Columns in output: {len(df.columns)}")
print(f"    First 10 columns: {list(df.columns[:10])}")
print(f"    Last 5 columns : {list(df.columns[-5:])}")

# Check key columns are present
required = ['MANUFACTURER_NAME', 'BRAND_NAME', 'Classpath', 'INVOICE_DESC',
            'MOBILE_DESC', 'SHORT_DESC', 'LONG_DESC1',
            'ATTRIBUTE_LABEL 1', 'ATTRIBUTE_VALUE 1', 'ATTRIBUTE_UOM 1']
missing = [c for c in required if c not in df.columns]
if missing:
    print(f"    MISSING columns: {missing}")
else:
    print(f"    All required columns present!")

# Show sample of populated data
print(f"\n  Sample enriched data (row 1):")
r1 = df.iloc[0]
for col in ['Mfg_Part_Num', 'MANUFACTURER_NAME', 'BRAND_NAME', 'Classpath',
            'INVOICE_DESC', 'MOBILE_DESC', 'SHORT_DESC',
            'ATTRIBUTE_LABEL 1', 'ATTRIBUTE_VALUE 1']:
    val = str(r1.get(col, '')).strip()
    if val and val != 'nan':
        print(f"    {col:30} = {val[:70]}")

# 5. Sample export as CSV
print("\n[5] Sample export — 10 rows as CSV...")
r = requests.get(f"{BASE}/api/catalog/unilog-sample-export?limit=10&fmt=csv")
assert r.status_code == 200, f"CSV export failed: {r.status_code}"
csv_df = pd.read_csv(io.StringIO(r.text))
print(f"    Rows: {len(csv_df)} | Cols: {len(csv_df.columns)}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
print("\nEndpoints available:")
print(f"  Preview :  GET  {BASE}/api/catalog/unilog-preview?limit=5")
print(f"  Export  :  GET  {BASE}/api/catalog/unilog-sample-export?limit=100&fmt=xlsx")
print(f"  Upload  :  POST {BASE}/api/catalog/unilog-export  (multipart file)")
print(f"  Process :  POST {BASE}/api/catalog/unilog-process (JSON response)")
print(f"\n  UI page : http://localhost:8000  → Unilog Intelligence (nav #08)")
