"""add a Show's flyer and more-info link, and a Venue's calendar page (app/ingestion/venue_calendar.py)

Revision ID: a1b2c3d4e5f6
Revises: c2e4a6b8d0f1
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c2e4a6b8d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("flyer_image_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("more_info_url", sa.String(500), nullable=True))
    with op.batch_alter_table("venues") as batch:
        batch.add_column(sa.Column("calendar_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("calendar_checked_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("calendar_read_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("calendar_retry_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("venues") as batch:
        batch.drop_column("calendar_retry_at")
        batch.drop_column("calendar_read_at")
        batch.drop_column("calendar_checked_at")
        batch.drop_column("calendar_url")
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("more_info_url")
        batch.drop_column("flyer_image_url")
