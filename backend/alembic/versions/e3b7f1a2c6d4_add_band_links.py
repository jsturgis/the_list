"""add MusicBrainz's links to bands (every artist-to-URL relationship: type and URL)

Revision ID: e3b7f1a2c6d4
Revises: d7a4e2c9b815
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3b7f1a2c6d4"
down_revision: Union[str, None] = "d7a4e2c9b815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("links", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("links")
