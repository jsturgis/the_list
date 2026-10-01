"""add a ticket link to shows (from the enriched List export)

Revision ID: c4d82b1e6f93
Revises: a3c51e8f2d07
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d82b1e6f93"
down_revision: Union[str, None] = "a3c51e8f2d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("ticket_url", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("ticket_url")
