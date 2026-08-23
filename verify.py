import requests, io, pandas as pd

BASE = 'http://localhost:8000'

r = requests.get(BASE + '/api/catalog/unilog-preview?limit=5')
prev = r.json()
print('Preview rows:', prev['total'], '| mode:', prev['enrichment_mode'])
for row in prev['rows']:
    mpn   = row.get('Mfg_Part_Num', '')
    brand = row.get('BRAND_NAME', '')
    conf  = row.get('_confidence', '')
    rev   = row.get('_needs_review', '')
    cp    = row.get('Classpath', '')
    inv   = row.get('INVOICE_DESC', '')
    attrs = [(a['label'], a['value']) for a in row.get('attributes', [])[:4]]
    print(f'  MPN={mpn} | Brand={brand} | Conf={conf} | Review={rev}')
    print(f'    Classpath : {cp}')
    print(f'    INVOICE   : {inv}')
    if attrs:
        print(f'    Attrs     : {attrs}')

r2 = requests.get(BASE + '/api/catalog/unilog-sample-export?limit=10&fmt=xlsx')
df = pd.read_excel(io.BytesIO(r2.content))
print()
print('Export:', len(df), 'rows x', len(df.columns), 'cols')
ok = 'ATTRIBUTE_LABEL 1' in df.columns
print('All required cols present:', ok)
row1 = df.iloc[0]
print('BRAND_NAME   :', row1['BRAND_NAME'])
print('Classpath    :', row1['Classpath'])
print('INVOICE_DESC :', row1['INVOICE_DESC'])
print('SHORT_DESC   :', row1['SHORT_DESC'])
print('ATTR 1       :', row1.get('ATTRIBUTE_LABEL 1'), '=', row1.get('ATTRIBUTE_VALUE 1'))
print()
print('DONE')
