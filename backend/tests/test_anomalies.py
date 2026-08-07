from app.services.anomalies import detect_anomalies


class FakeItem:
    def __init__(self, price, qty=1.0, cat=None):
        self.unit_price = price
        self.quantity = qty
        self.category_label = cat
        self.id = 0
        self.description = "test"
        self.supplier = "Test Supplier"


def test_detects_outlier():
    items = [FakeItem(10) for _ in range(10)] + [FakeItem(10000)]
    for i in items:
        i.category_label = "Office Supplies"
    results = detect_anomalies(items)
    flagged = [r for r in results if r["is_anomaly"]]
    assert len(flagged) == 1
    assert flagged[0]["description"] == "test"


def test_detects_quantity_outlier():
    items = [FakeItem(10, qty=1) for _ in range(10)] + [FakeItem(10, qty=100)]
    for i in items:
        i.category_label = "Office Supplies"
    results = detect_anomalies(items)
    flagged = [r for r in results if r["is_anomaly"]]
    assert len(flagged) >= 1


def test_zscore_is_not_flattened_to_zero():
    """The final merge step used to overwrite every result's zscore with a
    flat 0.0, discarding the real computed deviation - even for a wildly
    anomalous item."""
    items = [FakeItem(10) for _ in range(10)] + [FakeItem(10000)]
    for i in items:
        i.category_label = "Office Supplies"
    results = detect_anomalies(items)
    flagged = [r for r in results if r["is_anomaly"]]
    assert len(flagged) == 1
    assert abs(flagged[0]["zscore"]) > 2.5
