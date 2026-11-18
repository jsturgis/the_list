"""keep the warnings an ingest logged on its run, for the maintainer's email

Revision ID: d0f2a4b6c8e3
Revises: c9e1f3a5b7d2
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0f2a4b6c8e3"
down_revision: Union[str, None] = "c9e1f3a5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("warnings", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_column("warnings")
