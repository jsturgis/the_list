"""add new-Band stats to ingestion runs: how many, the share without a photo, and the share that fell back to the
edition for genres, photo and links

Revision ID: a9d2e4f6b1c3
Revises: f1c8a3d5b2e7
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9d2e4f6b1c3"
down_revision: Union[str, None] = "f1c8a3d5b2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PCTS = ("new_bands_without_photo_pct", "new_bands_photo_from_edition_pct", "new_bands_genres_from_edition_pct",
         "new_bands_links_from_edition_pct")


def upgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("new_bands", sa.Integer(), nullable=True))
        for column in _PCTS:
            batch.add_column(sa.Column(column, sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        for column in ("new_bands", *_PCTS):
            batch.drop_column(column)
