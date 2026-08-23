"""add embedding_cache to line_items

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("line_items", sa.Column("embedding_cache", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("line_items", "embedding_cache")