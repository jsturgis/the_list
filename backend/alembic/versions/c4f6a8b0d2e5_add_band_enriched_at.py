"""add when a Band was last looked up on the services (MusicBrainz, Wikimedia, Last.fm, Discogs)

Revision ID: c4f6a8b0d2e5
Revises: b3e5c7d9f1a2
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f6a8b0d2e5"
down_revision: Union[str, None] = "b3e5c7d9f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("enriched_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        batch.drop_column("enriched_at")
