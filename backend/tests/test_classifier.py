from app.services import classifier
from app.services.classifier import classify_batch, classify_description, seed_feedback_exemplars


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


def test_feedback_overrides_rule_based_match():
    """A user correction on a description that DOES contain a rule-based
    keyword must actually change future classifications of similar
    descriptions - not be silently ignored because rule_based short-circuits
    before feedback is ever consulted."""
    original = {c: list(v) for c, v in classifier._FEEDBACK_EXEMPLARS.items()}
    try:
        desc = "Laptop Dell Precision workstation for legal department"

        before = classify_description(desc)
        assert before["method"] == "rule_based"
        assert before["category"] == "Computer Equipment & Accessories"

        # User corrects it: this laptop purchase was actually for the legal
        # team's professional services budget, not IT hardware. classify_description
        # defaults to role="buyer" (see calls above/below), so the exemplar
        # must target that same pool to be picked back up.
        seed_feedback_exemplars([(desc, "Professional & Consulting Services", "buyer")])

        after = classify_description(desc)
        assert after["category"] == "Professional & Consulting Services"
        assert after["method"] == "feedback"
    finally:
        classifier._FEEDBACK_EXEMPLARS.clear()
        classifier._FEEDBACK_EXEMPLARS.update(original)


def test_llm_confidence_is_clamped_to_valid_range(monkeypatch):
    """A malformed-but-valid LLM response with an out-of-range confidence
    (e.g. 999) must not be trusted as-is - it should be clamped to [0, 1]."""
    monkeypatch.setattr(
        classifier, "chat",
        lambda messages: '{"category": "Travel & Transportation", "confidence": 999}',
    )
    result = classifier._llm_based("some ambiguous description")
    assert result is not None
    _, conf = result
    assert 0.0 <= conf <= 1.0

