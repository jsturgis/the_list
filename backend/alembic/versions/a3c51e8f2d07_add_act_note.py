"""add a note to acts (the parenthetical after a name, e.g. its members)

Revision ID: a3c51e8f2d07
Revises: 7e2a1c9d4b10
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c51e8f2d07"
down_revision: Union[str, None] = "7e2a1c9d4b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("acts") as batch:
        batch.add_column(sa.Column("note", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("acts") as batch:
        batch.drop_column("note")
