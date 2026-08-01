from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    detail: str


class Paginated(BaseModel):
    total: int
    page: int
    page_size: int
    items: list
