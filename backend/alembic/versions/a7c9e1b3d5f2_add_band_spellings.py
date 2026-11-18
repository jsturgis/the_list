"""keep the spellings a Band was listed under that a service put right ("Sunamo" for Sunami)

Revision ID: a7c9e1b3d5f2
Revises: 1d7a0db85b6d
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1b3d5f2"
down_revision: Union[str, None] = "1d7a0db85b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("spellings", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("spellings")
