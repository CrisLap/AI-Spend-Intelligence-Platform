from app.services.duplicates import find_duplicates


class FakeItem:
    def __init__(self, desc, total, supplier=None, inv_num=None):
        self.id = 0
        self.description = desc
        self.total = total
        self.supplier = supplier
        self.invoice_number = inv_num
        self.embedding_cache = None  # find_duplicates reads/writes this, mirroring LineItem's real column


def test_exact_invoice_duplicate():
    items = [
        FakeItem("Toner HP", 180.0, "Office Depot", "INV-001"),
        FakeItem("Toner HP", 180.0, "Office Depot", "INV-001"),
    ]
    groups = find_duplicates(items)
    assert len(groups) == 1
    assert len(groups[0]["items"]) == 2


def test_same_invoice_different_products_are_not_duplicates():
    """Two distinct line items on the same invoice, with coincidentally
    similar amounts, must NOT be flagged as duplicates just because they
    share supplier + invoice_number + a close total."""
    items = [
        FakeItem("Laptop Dell Latitude 5540", 900.0, "Dell Technologies", "DELL-001"),
        FakeItem("Notebook HP EliteBook 840", 901.0, "Dell Technologies", "DELL-001"),
    ]
    groups = find_duplicates(items)
    assert groups == []


def test_exact_match_reports_similarity_of_one():
    items = [
        FakeItem("Toner HP", 180.0, "Office Depot", "INV-001"),
        FakeItem("Toner HP", 180.0, "Office Depot", "INV-001"),
    ]
    groups = find_duplicates(items)
    assert groups[0]["similarity"] == 1.0


def test_semantic_match_reports_its_real_similarity_not_a_fake_one():
    """A group formed only via embedding similarity (not an exact
    supplier+invoice+description match) must report the real computed
    score, not always claim 100% similarity."""
    items = [
        FakeItem("Toner cartridge HP LaserJet 415A black", 180.0),
        FakeItem("Toner cartridge HP LaserJet 415A colour", 180.0),
    ]
    groups = find_duplicates(items, threshold=0.5)
    assert len(groups) == 1
    assert 0.5 <= groups[0]["similarity"] < 1.0
