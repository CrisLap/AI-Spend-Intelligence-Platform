"""Focused edge-case coverage for app.services.agents.tools that isn't
already exercised by tests/test_chat_react.py (which covers the
happy-path ranking and its wiring into the ReAct tool registry)."""
from __future__ import annotations

from app.core.security import hash_password
from app.models.document import Document, LineItem
from app.models.user import User
from app.services.agents.tools import top_expenses_tool_for


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, description: str, supplier: str, total: float) -> None:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(LineItem(document_id=doc.id, description=description, supplier=supplier, total=total))
    db.commit()


def test_top_expenses_defaults_to_five_when_input_is_empty_or_non_numeric(db):
    owner = _make_user(db, "tt-default@test.com")
    for i in range(7):
        _make_item(db, owner, f"Item {i}", "Supplier", float(i))

    tool = top_expenses_tool_for(owner.id, db)

    assert len(tool.fn("").splitlines()) == 5
    assert len(tool.fn("   ").splitlines()) == 5
    assert len(tool.fn("not a number").splitlines()) == 5


def test_top_expenses_clamps_requested_count_between_one_and_twenty(db):
    owner = _make_user(db, "tt-clamp@test.com")
    for i in range(25):
        _make_item(db, owner, f"Item {i}", "Supplier", float(i))

    tool = top_expenses_tool_for(owner.id, db)

    # "0" is not a positive count, but str.isdigit() still parses it, so the
    # result must be clamped up to at least 1, not silently return nothing.
    assert len(tool.fn("0").splitlines()) == 1
    # A count above the dataset size but within [1, 20] should still be
    # clamped to at most 20 (not returned as an unbounded/huge result).
    assert len(tool.fn("999").splitlines()) == 20


def test_top_expenses_returns_a_message_when_user_has_no_line_items(db):
    owner = _make_user(db, "tt-empty@test.com")

    tool = top_expenses_tool_for(owner.id, db)

    assert tool.fn("5") == "No line items found for this user."


def test_top_expenses_only_ranks_the_requesting_users_own_items(db):
    owner = _make_user(db, "tt-owner@test.com")
    other = _make_user(db, "tt-other@test.com")
    _make_item(db, owner, "Owner item", "Supplier", 100.0)
    _make_item(db, other, "Other user's huge expense", "Supplier", 999999.0)

    tool = top_expenses_tool_for(owner.id, db)

    result = tool.fn("5")
    assert "Owner item" in result
    assert "Other user's huge expense" not in result
