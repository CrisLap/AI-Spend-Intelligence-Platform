from __future__ import annotations

import io
import os
import re
import uuid
from pathlib import Path

import pandas as pd
from PIL import Image
from pypdf import PdfReader

from app.core.config import settings
from app.services.ai import chat
from app.services.executor import run_cpu_bound

# Explicit decompression-bomb guard: an uploaded image with an enormous
# pixel count (possible even within the 50MB upload size cap, e.g. a highly
# compressed PNG) can exhaust CPU/RAM during OCR. Pillow's own default is
# similar but left implicit; pin it explicitly so it can't silently change.
Image.MAX_IMAGE_PIXELS = 50_000_000

_EXTRACT_ITEMS_INVOICE_PROMPT = (
    "You are a specialized assistant for extracting data from invoices. "
    "Analyze the following invoice text and return a JSON array of objects with fields: "
    "description (string), quantity (number), unit_price (number), total (number), "
    "supplier (string or null), invoice_number (string or null), invoice_date (ISO string or null). "
    "If a field is not present in the text, use null. Return ONLY the JSON, no other text.\n\nText:\n{text}"
)

_EXTRACT_ITEMS_ORDER_PROMPT = (
    "You are a specialized assistant for extracting data from purchase orders. "
    "Analyze the following purchase order text and return a JSON array of objects with fields: "
    "description (string), quantity (number), unit_price (number), total (number), "
    "supplier (string or null), order_number (string or null), order_date (ISO string or null). "
    "If a field is not present in the text, use null. Return ONLY the JSON, no other text.\n\nText:\n{text}"
)

_EXTRACT_ITEMS_CONTRACT_PROMPT = (
    "You are a specialized assistant for extracting data from contracts. "
    "Analyze the following contract text and return a JSON array of objects with fields: "
    "description (string), quantity (number), unit_price (number), total (number), "
    "supplier (string or null), contract_number (string or null), start_date (ISO string or null), end_date (ISO string or null). "
    "If a field is not present in the text, use null. Return ONLY the JSON, no other text.\n\nText:\n{text}"
)

_EXTRACT_ITEMS_GENERIC_PROMPT = (
    "You are a specialized assistant for extracting data from procurement documents. "
    "Analyze the following document text and return a JSON array of objects with fields: "
    "description (string), quantity (number), unit_price (number), total (number), "
    "supplier (string or null), invoice_number (string or null), invoice_date (ISO string or null). "
    "If a field is not present in the text, use null. Return ONLY the JSON, no other text.\n\nText:\n{text}"
)


def ocr_image(content: bytes) -> str:
    try:
        import pytesseract
        img = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(img, lang="ita+eng")
    except ImportError:
        return "[OCR not available: install pytesseract and tesseract-ocr]"


async def ocr_image_async(content: bytes) -> str:
    return await run_cpu_bound(ocr_image, content)


def extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def extract_text_from_pdf_async(content: bytes) -> str:
    return await run_cpu_bound(extract_text_from_pdf, content)


def extract_text_from_image(content: bytes) -> str:
    return ocr_image(content)


def extract_text_from_excel(content: bytes) -> str:
    df = pd.read_excel(io.BytesIO(content))
    return df.to_string(index=False)


def extract_text_from_csv(content: bytes) -> str:
    df = pd.read_csv(io.BytesIO(content))
    return df.to_string(index=False)


def save_upload(content: bytes, original_name: str) -> tuple[str, str]:
    stem, ext = os.path.splitext(original_name)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)[:60]
    uid = uuid.uuid4().hex[:12]
    filename = f"{safe}_{uid}{ext}"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = str(upload_dir / filename)
    with open(path, "wb") as f:
        f.write(content)
    return filename, path


def extract_raw_text(file_path: str, filename: str) -> str:
    with open(file_path, "rb") as f:
        content = f.read()
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(content)
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        return extract_text_from_image(content)
    elif ext in (".xlsx", ".xls"):
        return extract_text_from_excel(content)
    elif ext == ".csv":
        return extract_text_from_csv(content)
    return ""


_NUM = r"\d[\d.,]*\d|\d"
_LINE_ITEM_RE = re.compile(
    rf"^(?P<desc>.+?)\s{{2,}}(?P<qty>{_NUM})\s+(?P<price>{_NUM})\s+(?P<total>{_NUM})(?:\s+\S.*)?$"
)


def _to_float(raw: str) -> float:
    raw = raw.strip()
    if "." in raw and "," in raw:
        # Both separators present: whichever comes last is the decimal
        # separator (e.g. "1.234,56" -> decimal ",", thousands ".";
        # "1,234.56" -> decimal ".", thousands ",").
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        raw = raw.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif raw.count(",") > 1:
        raw = raw.replace(",", "")  # e.g. "1,234,567" - comma-only thousands grouping
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")  # e.g. "1.234.567" - dot-only thousands grouping
    else:
        raw = raw.replace(",", ".")  # single separator: treat as decimal (unchanged default)
    return float(raw)


def _try_parse_regex(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        m = _LINE_ITEM_RE.match(line.strip())
        if not m:
            continue
        items.append({
            "description": m.group("desc").strip(),
            "quantity": _to_float(m.group("qty")),
            "unit_price": _to_float(m.group("price")),
            "total": _to_float(m.group("total")),
        })
    return items


def parse_items(text: str, doc_type: str | None = None) -> list[dict]:
    items = _try_parse_regex(text)
    if items:
        return items
    try:
        prompt_map = {
            "invoice": _EXTRACT_ITEMS_INVOICE_PROMPT,
            "order": _EXTRACT_ITEMS_ORDER_PROMPT,
            "contract": _EXTRACT_ITEMS_CONTRACT_PROMPT,
        }
        prompt = prompt_map.get(doc_type or "", _EXTRACT_ITEMS_GENERIC_PROMPT)
        result = chat([{"role": "user", "content": prompt.format(text=text[:8000])}])
        if "[" in result:
            import json
            parsed = json.loads(result[result.index("["):result.rindex("]") + 1])
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


# Header aliases for structured (CSV/Excel) files, so an ERP export with its
# own column names ("Vendor", "Qty", "PO Number") still maps onto the fields
# the rest of the pipeline expects. Matching is on the normalized header
# (lower-case, spaces/dashes -> underscores).
TABULAR_ALIASES: dict[str, set[str]] = {
    "description": {"description", "descrizione", "item", "item_description", "articolo"},
    "quantity": {"quantity", "qty", "quantita", "quantità", "qta"},
    "unit_price": {"unit_price", "unitprice", "price", "prezzo", "prezzo_unitario"},
    "total": {"total", "totale", "amount", "importo", "line_total"},
    "supplier": {"supplier", "vendor", "fornitore"},
    "invoice_number": {"invoice_number", "invoice", "numero_fattura", "po_number", "order_number"},
    "invoice_date": {"invoice_date", "date", "data", "order_date"},
}
# Column widths of LineItem (models/document.py)
_TEXT_LIMITS = {"supplier": 300, "invoice_number": 100, "invoice_date": 20}


def _cell_number(value) -> float | None:
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    try:
        return float(value) if isinstance(value, (int, float)) else _to_float(str(value))
    except (ValueError, TypeError):
        return None


def _cell_text(value, limit: int) -> str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip()
    return text[:limit] or None


def parse_tabular_items(file_path: str, filename: str) -> list[dict] | None:
    """Parses a structured CSV/Excel file straight into line-item dicts,
    keeping the supplier / invoice number / date columns that the plain-text
    regex path (parse_items) cannot see. Returns None - so the caller falls
    back to parse_items - when the file isn't tabular or has no recognizable
    description and amount columns."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        return None
    try:
        df = pd.read_csv(file_path) if ext == ".csv" else pd.read_excel(file_path)
    except Exception:
        return None

    columns: dict[str, str] = {}
    for col in df.columns:
        key = re.sub(r"[\s-]+", "_", str(col).strip().lower())
        for canonical, aliases in TABULAR_ALIASES.items():
            if key in aliases and canonical not in columns:
                columns[canonical] = col
    if "description" not in columns or not ({"total", "unit_price"} & columns.keys()):
        return None

    items: list[dict] = []
    for _, row in df.iterrows():
        description = _cell_text(row[columns["description"]], 500)
        if not description:
            continue
        quantity = _cell_number(row[columns["quantity"]]) if "quantity" in columns else None
        quantity = quantity if quantity else 1.0
        unit_price = _cell_number(row[columns["unit_price"]]) if "unit_price" in columns else None
        total = _cell_number(row[columns["total"]]) if "total" in columns else None
        if total is None and unit_price is not None:
            total = round(quantity * unit_price, 2)
        if total is None:
            continue
        if unit_price is None:
            unit_price = round(total / quantity, 2)
        item = {"description": description, "quantity": quantity, "unit_price": unit_price, "total": total}
        for field, limit in _TEXT_LIMITS.items():
            if field in columns:
                item[field] = _cell_text(row[columns[field]], limit)
        items.append(item)
    return items or None


_METADATA_RE = re.compile(
    r"(?:fattura\s*n\.?|invoice\s*(?:number|no\.?)|numero\s*fattura|"
    r"fattura|numero|n\.|invoice|no\.?|number)"
    r"\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-/]*)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})")
_SUPPLIER_RE = re.compile(
    r"(?:supplier|vendor|company|fornitore|venditore|azienda)\s*[:#]?\s*(.+)",
    re.IGNORECASE,
)


def extract_metadata(text: str) -> dict:
    inv_num = None
    inv_date = None
    supplier = None
    m = _METADATA_RE.search(text)
    if m:
        inv_num = m.group(1)
    m = _DATE_RE.search(text)
    if m:
        inv_date = m.group(1)
    m = _SUPPLIER_RE.search(text)
    if m:
        supplier = m.group(1).strip()
    return {"invoice_number": inv_num, "invoice_date": inv_date, "supplier": supplier}

