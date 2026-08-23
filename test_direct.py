"""
Direct enrichment test — no server needed.
Tests the Unilog enrichment engine and generates an output file.
"""
import sys, io, pandas as pd

sys.path.insert(0, '.')
from backend.catalog.unilog_enrichment import enrich_unilog_row

PHOLDS = {
    '-- unbranded --', '-- no unilog brand --', '-- no dib brand --',
    '-', 'commodity - unbranded'
}

# Load input
df_in = pd.read_csv('Unihack_ Sample Dataset - Input.csv').head(20)
rows_in = df_in.to_dict(orient='records')
for row in rows_in:
    for k, v in list(row.items()):
        if str(v).strip().lower() in PHOLDS:
            row[k] = ''

# Enrich
results = [enrich_unilog_row(r) for r in rows_in]

# Print quality report
print("=" * 65)
print("UNILOG ENRICHMENT — Quality Report (first 20 rows)")
print("=" * 65)

classified = sum(1 for r in results if "Uncategorized" not in r.get("Classpath", ""))
branded    = sum(1 for r in results if r.get("BRAND_NAME") and r.get("BRAND_NAME") != r.get("MANUFACTURER_NAME"))
has_attrs  = sum(1 for r in results if r.get("ATTRIBUTE_LABEL 1"))
avg_conf   = sum(float(r.get("_confidence", 0)) for r in results) / len(results)
needs_rev  = sum(1 for r in results if r.get("_needs_review") == "Yes")

print(f"Classified with Classpath : {classified}/{len(results)} ({100*classified//len(results)}%)")
print(f"Brand extracted from desc : {branded}/{len(results)} ({100*branded//len(results)}%)")
print(f"Has attributes            : {has_attrs}/{len(results)} ({100*has_attrs//len(results)}%)")
print(f"Avg confidence score      : {avg_conf:.0%}")
print(f"Needs human review        : {needs_rev}/{len(results)}")
print()

# Show 5 sample rows
for r in results[:5]:
    mpn  = r.get("Mfg_Part_Num", "")
    conf = r.get("_confidence", "")
    rev  = r.get("_needs_review", "")
    print(f"MPN: {mpn}")
    print(f"  Manufacturer : {r.get('MANUFACTURER_NAME','')}")
    print(f"  Brand        : {r.get('BRAND_NAME','')}")
    print(f"  Classpath    : {r.get('Classpath','')}")
    print(f"  INVOICE_DESC : {r.get('INVOICE_DESC','')}")
    print(f"  SHORT_DESC   : {r.get('SHORT_DESC','')}")
    a1 = r.get("ATTRIBUTE_LABEL 1",""); v1 = r.get("ATTRIBUTE_VALUE 1",""); u1 = r.get("ATTRIBUTE_UOM 1","")
    if a1:
        print(f"  Attr 1       : {a1} = {v1} {u1}".strip())
    print(f"  Confidence   : {conf} | NeedsReview: {rev}")
    print()

# Save output XLSX
# Remove internal metadata cols
OUT_COLS = [c for c in results[0].keys() if not c.startswith("_")]
df_out = pd.DataFrame(results)[OUT_COLS]

out_file = "unilog_enriched_output.xlsx"
df_out.to_excel(out_file, index=False, engine="openpyxl")
print(f"Saved: {out_file}")
print(f"Rows: {len(df_out)} | Columns: {len(df_out.columns)}")
print()
print("DONE")
