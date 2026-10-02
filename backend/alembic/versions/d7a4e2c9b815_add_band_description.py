"""add a description to bands (the enriched export's artist note)

Revision ID: d7a4e2c9b815
Revises: c4d82b1e6f93
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a4e2c9b815"
down_revision: Union[str, None] = "c4d82b1e6f93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("description")
