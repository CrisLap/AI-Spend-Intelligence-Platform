from app.services.document_intelligence import _try_parse_regex, extract_metadata, parse_items


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


def test_regex_based_fallback():
    text = "Item    1    10.50    10.50\nPart    3    20.00    60.00"
    items = _try_parse_regex(text)
    assert len(items) == 2
    assert items[0]["total"] == 10.50
