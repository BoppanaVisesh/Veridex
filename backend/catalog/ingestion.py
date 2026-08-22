"""
Catalog Intelligence — File Ingestion Module (§Catalog)

Parses uploaded catalog files (CSV, XLSX, HTML, PDF) into a standardized
intermediate structure of candidate product fields and raw evidence.
"""

from __future__ import annotations

import io
import re
from typing import Optional, Any
from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader

from backend.catalog.catalog_models import RawSourceType


def parse_csv_or_excel(
    file_bytes: bytes,
    filename: str,
    default_product_name: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Parse CSV or XLSX file into intermediate product structure.
    Each row -> one Product.
    Each column -> one ProductField.
    """
    lower_fn = filename.lower()
    if lower_fn.endswith('.xlsx') or lower_fn.endswith('.xls'):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        df = pd.read_csv(io.BytesIO(file_bytes))

    products = []
    headers = [str(col).strip() for col in df.columns]

    # Find potential name column
    name_col = None
    for col in headers:
        if col.lower() in ('name', 'product_name', 'product name', 'title', 'item_name', 'product'):
            name_col = col
            break

    for row_idx, row in df.iterrows():
        row_num = row_idx + 1
        
        # Determine product name
        if default_product_name and len(df) == 1:
            p_name = default_product_name
        elif name_col and pd.notna(row[name_col]):
            p_name = str(row[name_col]).strip()
        elif default_product_name:
            p_name = f"{default_product_name} - Row {row_num}"
        else:
            p_name = f"Catalog Item #{row_num} ({filename})"

        fields = []
        for col in headers:
            cell_val = row[col]
            if pd.isna(cell_val):
                continue
            val_str = str(cell_val).strip()
            if not val_str or val_str.lower() in ('nan', 'null', 'none'):
                continue

            fields.append({
                "field_name": col,
                "raw_value": val_str,
                "source_label": f"{filename} row {row_num}"
            })

        products.append({
            "product_name": p_name,
            "raw_source_type": RawSourceType.CSV,
            "fields": fields
        })

    return products


def parse_html(
    file_bytes: bytes,
    filename: str,
    default_product_name: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Parse HTML product page into intermediate candidate fields.
    Extracts title, meta tags, table rows, definition lists, and key-value pairs.
    """
    html_content = file_bytes.decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html_content, 'html.parser')

    # Product Name
    title_tag = soup.find('h1') or soup.find('title')
    extracted_name = title_tag.get_text().strip() if title_tag else filename.split('.')[0]
    p_name = default_product_name or extracted_name or f"HTML Product ({filename})"

    fields = []

    # 1. Meta tags (e.g. og:title, product:price)
    for meta in soup.find_all('meta'):
        name = meta.get('name') or meta.get('property')
        content = meta.get('content')
        if name and content:
            fields.append({
                "field_name": name.strip(),
                "raw_value": content.strip(),
                "source_label": f"{filename} meta tag"
            })

    # 2. Table rows (<tr><th>key</th><td>val</td></tr>)
    for t_idx, table in enumerate(soup.find_all('table'), 1):
        for r_idx, tr in enumerate(table.find_all('tr'), 1):
            th = tr.find('th')
            tds = tr.find_all('td')
            if th and tds:
                k = th.get_text().strip()
                v = tds[0].get_text().strip()
                if k and v:
                    fields.append({
                        "field_name": k,
                        "raw_value": v,
                        "source_label": f"{filename} table {t_idx} row {r_idx}"
                    })
            elif len(tds) >= 2:
                k = tds[0].get_text().strip()
                v = tds[1].get_text().strip()
                if k and v and len(k) <= 40:
                    fields.append({
                        "field_name": k,
                        "raw_value": v,
                        "source_label": f"{filename} table {t_idx} row {r_idx}"
                    })

    # 3. Definition lists (<dt>key</dt><dd>val</dd>)
    dts = soup.find_all('dt')
    dds = soup.find_all('dd')
    for dt, dd in zip(dts, dds):
        k = dt.get_text().strip()
        v = dd.get_text().strip()
        if k and v:
            fields.append({
                "field_name": k,
                "raw_value": v,
                "source_label": f"{filename} definition list"
            })

    # 4. Text line key-value patterns (e.g. <b>Voltage:</b> 240V or <p>Weight: 10kg</p>)
    for line_idx, elem in enumerate(soup.find_all(['p', 'li', 'div']), 1):
        txt = elem.get_text().strip()
        if ':' in txt and len(txt) < 200:
            parts = txt.split(':', 1)
            k, v = parts[0].strip(), parts[1].strip()
            if k and v and len(k) <= 35 and not k.startswith('<') and '\n' not in k:
                fields.append({
                    "field_name": k,
                    "raw_value": v,
                    "source_label": f"{filename} section {line_idx}"
                })

    return [{
        "product_name": p_name,
        "raw_source_type": RawSourceType.HTML,
        "fields": fields
    }]


def parse_pdf(
    file_bytes: bytes,
    filename: str,
    default_product_name: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Parse PDF spec sheet into intermediate candidate fields.
    Extracts text, parses key:value pairs, and groups remaining unparsed text into a blob.
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    fields = []
    unparsed_lines = []

    p_name = default_product_name or filename.split('.')[0]

    for p_idx, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        for l_idx, line in enumerate(lines, 1):
            if ':' in line and len(line) < 150:
                parts = line.split(':', 1)
                k, v = parts[0].strip(), parts[1].strip()
                if k and v and len(k) <= 35 and re.match(r'^[A-Za-z0-9\s_\-\(\)/]+$', k):
                    fields.append({
                        "field_name": k,
                        "raw_value": v,
                        "source_label": f"{filename} page {p_idx} line {l_idx}"
                    })
                    continue
            unparsed_lines.append(line)

    if unparsed_lines:
        fields.append({
            "field_name": "spec_sheet_text",
            "raw_value": "\n".join(unparsed_lines[:50]),
            "source_label": f"{filename} text blob"
        })

    return [{
        "product_name": p_name,
        "raw_source_type": RawSourceType.PDF,
        "fields": fields
    }]


def parse_uploaded_file(
    file_bytes: bytes,
    filename: str,
    product_name: Optional[str] = None
) -> list[dict[str, Any]]:
    """Unified entry point for catalog file ingestion."""
    lower_fn = filename.lower()
    if lower_fn.endswith('.csv') or lower_fn.endswith('.xlsx') or lower_fn.endswith('.xls'):
        return parse_csv_or_excel(file_bytes, filename, product_name)
    elif lower_fn.endswith('.html') or lower_fn.endswith('.htm'):
        return parse_html(file_bytes, filename, product_name)
    elif lower_fn.endswith('.pdf'):
        return parse_pdf(file_bytes, filename, product_name)
    else:
        # Fallback for text files
        return parse_pdf(file_bytes, filename, product_name)
