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


_LINE_ITEM_RE = re.compile(
    r"^(?P<desc>.+?)\s{2,}(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<price>\d+(?:[.,]\d+)?)\s+(?P<total>\d+(?:[.,]\d+)?)(?:\s+\S.*)?$"
)


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


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


_METADATA_RE = re.compile(r"(?:invoice|number|no\.?)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-/]*)", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})")
_SUPPLIER_RE = re.compile(r"(?:supplier|vendor|company)\s*[:#]?\s*(.+)", re.IGNORECASE)


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
