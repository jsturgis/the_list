"""add a Band's members (from Discogs): [{name, active}]

Revision ID: b3e5c7d9f1a2
Revises: a9d2e4f6b1c3
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e5c7d9f1a2"
down_revision: Union[str, None] = "a9d2e4f6b1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("members", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("members")
