from app.services.classifier import classify_batch, classify_description


def test_rule_based_office_supplies():
    r = classify_description("HP LaserJet Toner")
    assert r["category"] == "Office Equipment & Supplies"
    assert r["method"] == "rule_based"
    assert r["confidence"] >= 0.75


def test_rule_based_it_hardware():
    r = classify_description("Dell Latitude Laptop")
    assert r["category"] == "Computer Equipment & Accessories"


def test_classify_batch_preserves_order():
    descs = ["Toner HP", "Consulenza legale", "Volo Milano-Bruxelles"]
    results = classify_batch(descs)
    assert len(results) == 3
    assert [r["description"] for r in results] == descs
