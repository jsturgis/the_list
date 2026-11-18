"""keep the other names a Venue was listed under that matched it only through its Google place, so the ingest
doesn't look them up on Google Places every run

Revision ID: b8d0f2a4c6e1
Revises: a7c9e1b3d5f2
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0f2a4c6e1"
down_revision: Union[str, None] = "a7c9e1b3d5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.add_column(sa.Column("spellings", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.drop_column("spellings")
