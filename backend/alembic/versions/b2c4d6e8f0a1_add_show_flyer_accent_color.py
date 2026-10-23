"""add a Show's flyer accent colour (app/ingestion/flyer_color.py)

Revision ID: b2c4d6e8f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("flyer_accent_color", sa.String(7), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("flyer_accent_color")
