"""add agent_type to agent_runs

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("agent_type", sa.String(50), nullable=False, server_default="cost_saving"),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "agent_type")
