"""add a credit for a Band's photo (author, licence, licence URL, source page) for Wikimedia Commons photos

Revision ID: f1c8a3d5b2e7
Revises: e3b7f1a2c6d4
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1c8a3d5b2e7"
down_revision: Union[str, None] = "e3b7f1a2c6d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("image_credit", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("image_credit")
