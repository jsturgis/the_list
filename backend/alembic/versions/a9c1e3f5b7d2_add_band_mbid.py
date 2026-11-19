"""add a Band's MusicBrainz artist id (bands.mbid), kept from its lookup

Revision ID: a9c1e3f5b7d2
Revises: d0f2a4b6c8e3
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c1e3f5b7d2"
down_revision: Union[str, None] = "d0f2a4b6c8e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("mbid", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("mbid")
