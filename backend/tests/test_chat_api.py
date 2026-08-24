from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.chat import ChatMessage, ChatSession


def test_deleting_a_session_with_messages_does_not_violate_foreign_keys(client: TestClient, auth_headers: dict, db):
    """Deleting a chat session used to fail with a foreign key violation on
    Postgres whenever it had at least one message, since the messages were
    never cleaned up first."""
    from app.models.user import User
    user = db.query(User).filter(User.email == "test@spend.com").first()

    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(ChatMessage(session_id=session.id, role="user", content="ciao"))
    db.add(ChatMessage(session_id=session.id, role="assistant", content="ciao a te"))
    db.commit()

    r = client.delete(f"/chat/sessions/{session.id}", headers=auth_headers)
    assert r.status_code == 204


def test_list_sessions_scopes_by_user_and_includes_preview(client: TestClient, auth_headers: dict, db):
    """GET /chat/sessions must never leak another user's sessions, and each
    session's `preview` should be its first user message (used as the
    title in the frontend's chat history panel)."""
    from app.core.security import hash_password
    from app.models.user import User

    user = db.query(User).filter(User.email == "test@spend.com").first()
    other = User(
        email="other-chat-user@spend.com", hashed_password=hash_password("test1234567"),
        full_name="Other User", role="buyer",
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    mine = ChatSession(user_id=user.id)
    theirs = ChatSession(user_id=other.id)
    db.add_all([mine, theirs])
    db.commit()
    db.refresh(mine)
    db.refresh(theirs)
    db.add(ChatMessage(session_id=mine.id, role="user", content="What did we spend on office supplies last quarter?"))
    db.add(ChatMessage(session_id=mine.id, role="assistant", content="You spent $500."))
    db.add(ChatMessage(session_id=theirs.id, role="user", content="Should not appear for the other user"))
    db.commit()

    r = client.get("/chat/sessions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    ids = [s["id"] for s in body]
    assert mine.id in ids
    assert theirs.id not in ids

    mine_out = next(s for s in body if s["id"] == mine.id)
    assert mine_out["preview"] == "What did we spend on office supplies last quarter?"