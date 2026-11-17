"""record where a Show comes from: the List, or an event page added by hand (TicketWeb)

Revision ID: f3a5c7e9b1d4
Revises: d2f4b6a8c0e1
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a5c7e9b1d4"
down_revision: Union[str, None] = "d2f4b6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every Show so far is from the List.
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="list"))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("source")
