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