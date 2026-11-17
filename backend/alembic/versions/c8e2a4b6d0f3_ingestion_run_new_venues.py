"""ingestion runs count the Venues first seen in that ingest (new_venues), for the maintainer's email after a
successful ingest

Revision ID: c8e2a4b6d0f3
Revises: b7d1f3a5c9e2
Create Date: 2026-11-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2a4b6d0f3"
down_revision: Union[str, None] = "b7d1f3a5c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("new_venues", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_column("new_venues")
