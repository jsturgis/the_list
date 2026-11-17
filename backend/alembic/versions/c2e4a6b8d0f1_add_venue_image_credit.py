"""add a credit for a Venue's photo (author, licence, licence URL, source page) for Wikimedia Commons photos

Revision ID: c2e4a6b8d0f1
Revises: f3a5c7e9b1d4
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2e4a6b8d0f1"
down_revision: Union[str, None] = "f3a5c7e9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.add_column(sa.Column("image_credit", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.drop_column("image_credit")
