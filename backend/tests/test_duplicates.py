from app.services.duplicates import find_duplicates


class FakeItem:
    def __init__(self, desc, total, supplier=None, inv_num=None):
        self.id = 0
        self.description = desc
        self.total = total
        self.supplier = supplier
        self.invoice_number = inv_num


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
