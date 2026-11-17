"""two Shows can share a date, Venue and door time (a Venue with two rooms), so the unique constraint on them
(uq_show_identity) goes; ingest tells them apart by headliner

Downgrading puts the constraint back, which fails while two Shows share an identity.

Revision ID: d2f4b6a8c0e1
Revises: c8e2a4b6d0f3
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d2f4b6a8c0e1"
down_revision: Union[str, None] = "c8e2a4b6d0f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_constraint("uq_show_identity", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.create_unique_constraint("uq_show_identity", ["date", "venue_id", "door_time"])
