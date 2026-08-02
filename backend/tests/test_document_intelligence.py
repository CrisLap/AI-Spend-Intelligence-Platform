from app.services.document_intelligence import _to_float, _try_parse_regex, extract_metadata, parse_items


def test_parse_invoice_text():
    text = """Invoice INV-2024
Supplier: Office Depot
Date: 2024-06-15
Toner HP LaserJet    2    90.00    180.00
A4 Paper    5    12.00    60.00"""
    items = parse_items(text)
    assert len(items) >= 2
    assert items[0]["description"] == "Toner HP LaserJet"


def test_extract_metadata():
    text = "Invoice INV-2024\nSupplier: Office Depot\nDate: 2024-06-15"
    meta = extract_metadata(text)
    assert meta["invoice_number"] == "INV-2024"
    assert meta["supplier"] == "Office Depot"
    assert meta["invoice_date"] == "2024-06-15"


def test_extract_metadata_italian():
    """Real invoices in this platform are Italian - metadata extraction
    must not only recognize English keywords, or it silently returns
    null supplier/invoice_number for virtually every real upload."""
    text = "Fattura n. FT-2026-0042\nFornitore: Office Depot Italia Srl\nData: 15/01/2026"
    meta = extract_metadata(text)
    assert meta["invoice_number"] == "FT-2026-0042"
    assert meta["supplier"] == "Office Depot Italia Srl"
    assert meta["invoice_date"] == "15/01/2026"


def test_regex_based_fallback():
    text = "Item    1    10.50    10.50\nPart    3    20.00    60.00"
    items = _try_parse_regex(text)
    assert len(items) == 2
    assert items[0]["total"] == 10.50


def test_regex_based_fallback_handles_thousands_separator():
    """Italian-formatted amounts like '1.234,56' used the old single-
    separator regex/parser and were silently dropped entirely."""
    text = "Consulenza legale annuale    1    1.234,56    1.234,56"
    items = _try_parse_regex(text)
    assert len(items) == 1
    assert items[0]["unit_price"] == 1234.56
    assert items[0]["total"] == 1234.56


def test_to_float_disambiguates_separators():
    assert _to_float("44.00") == 44.0
    assert _to_float("45,00") == 45.0
    assert _to_float("1.234,56") == 1234.56
    assert _to_float("1,234.56") == 1234.56
    assert _to_float("1.234.567") == 1234567.0

