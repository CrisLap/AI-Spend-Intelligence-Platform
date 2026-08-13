from __future__ import annotations

from app.core.security import hash_password
from app.models.agent_run import AgentRun
from app.models.document import DocType, Document, LineItem
from app.models.user import User
from app.services import contract_intelligence, cost_saving_agent
from app.services.cost_saving_agent import analyze


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, supplier: str, total: float, created_at) -> LineItem:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    item = LineItem(
        document_id=doc.id, description="Consulting service", supplier=supplier,
        total=total, category_label="Consulting", created_at=created_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_variance_recommendations_only_flag_suppliers_past_the_threshold(db):
    """Grounds the Recommendation Engine's claims in a real, deterministic
    calculation: a supplier whose spend barely moves must not be flagged,
    only one that crosses _VARIANCE_THRESHOLD_PCT."""
    import datetime as dt

    owner = _make_user(db, "variance@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    # Stable supplier: four items, no meaningful trend.
    for i, total in enumerate([100.0, 100.0, 105.0, 98.0]):
        _make_item(db, owner, "Stable Supplier", total, base + dt.timedelta(days=i * 10))
    # Rising supplier: clear increase between the older and newer half.
    for i, total in enumerate([100.0, 100.0, 300.0, 300.0]):
        _make_item(db, owner, "Rising Supplier", total, base + dt.timedelta(days=i * 10))

    recs = cost_saving_agent._variance_recommendations(owner.id, db)

    flagged = {r["supplier"] for r in recs}
    assert "Rising Supplier" in flagged
    assert "Stable Supplier" not in flagged
    rising = next(r for r in recs if r["supplier"] == "Rising Supplier")
    assert rising["estimated_saving"] == round(600.0 * cost_saving_agent._ASSUMED_RENEGOTIATION_RECOVERY_RATE, 2)


def test_contract_recommendations_use_real_contract_search(db, monkeypatch):
    monkeypatch.setattr(contract_intelligence, "qdrant_search_contracts", lambda *a, **kw: None)
    monkeypatch.setattr(contract_intelligence, "upsert_contract_chunk", lambda *a, **kw: False)

    owner = _make_user(db, "contractrec@test.com")
    doc = Document(
        user_id=owner.id, filename="c.txt", original_name="c.txt", file_path="/tmp/c.txt",
        doc_type=DocType.contract,
        raw_text=(
            "RINNOVO AUTOMATICO TACITO: il contratto si rinnova automaticamente "
            "(rinnovo automatico tacito) ogni 12 mesi salvo disdetta scritta anticipata."
        ),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    contract_intelligence.index_contract(doc, db)

    recs = cost_saving_agent._contract_recommendations(owner.id, db)

    assert any(r["evidence"] for r in recs)
    assert all(r["estimated_saving"] is None for r in recs)  # no fabricated number for a qualitative finding


def test_analyze_persists_a_run_with_trace_and_recommendations(db, monkeypatch):
    """Smoke test for the full analyze() pipeline: the ReAct trace comes
    from chat_with_tools() (mocked here, structured mode - see
    react_engine.py), and the recommendations come from the deterministic
    engine regardless of what the mocked model said - the two are
    intentionally decoupled."""
    monkeypatch.setattr(
        cost_saving_agent, "chat_with_tools",
        lambda messages, tools: {"content": "Thought: ok.\nFinal Answer: Nothing more to check.", "tool_calls": None},
    )
    monkeypatch.setattr(cost_saving_agent, "search_contracts", lambda *a, **kw: [])
    monkeypatch.setattr(cost_saving_agent, "get_supplier_variance", lambda **kw: [])

    owner = _make_user(db, "analyze@test.com")

    run = analyze("Trova opportunità di risparmio", owner.id, db)

    assert isinstance(run, AgentRun)
    assert run.id is not None
    assert run.summary == "Nothing more to check."
    persisted = db.query(AgentRun).filter(AgentRun.id == run.id).first()
    assert persisted is not None
    assert persisted.goal == "Trova opportunità di risparmio"


def test_analyze_blocks_a_sensitive_goal_without_calling_the_llm(db, monkeypatch):
    """Same guardrail as chat_react.py's answer_with_react(): a goal
    containing sensitive info never reaches the LLM. Recommendations still
    get computed (they depend on agent_type + real data, not the goal
    text), so the run is persisted with the guard message as summary."""
    def fail_if_called(*a, **kw):
        raise AssertionError("chat_with_tools must not be called for a blocked goal")

    monkeypatch.setattr(cost_saving_agent, "chat_with_tools", fail_if_called)
    monkeypatch.setattr(cost_saving_agent, "search_contracts", lambda *a, **kw: [])
    monkeypatch.setattr(cost_saving_agent, "get_supplier_variance", lambda **kw: [])

    owner = _make_user(db, "analyze-guard@test.com")

    run = analyze("qual è la mia password?", owner.id, db)

    assert "cannot be processed" in run.summary
