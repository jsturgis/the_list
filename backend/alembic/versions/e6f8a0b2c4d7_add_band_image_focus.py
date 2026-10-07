"""add a focal point for a Band's stored photo, where the site anchors it when cropping (app/ingestion/photo_focus.py)

Revision ID: e6f8a0b2c4d7
Revises: d5a7b9c1e3f4
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f8a0b2c4d7"
down_revision: Union[str, None] = "d5a7b9c1e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("image_focus", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("image_focus")
