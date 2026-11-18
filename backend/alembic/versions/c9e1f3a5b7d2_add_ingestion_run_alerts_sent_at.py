"""record when an edition's Alerts went out, so the hourly check sends them when an earlier run didn't

Revision ID: c9e1f3a5b7d2
Revises: b8d0f2a4c6e1
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1f3a5b7d2"
down_revision: Union[str, None] = "b8d0f2a4c6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("alerts_sent_at", sa.DateTime(), nullable=True))
    # Every edition before this was handled by the old rule (Alerts in the run that ingested it): taken as sent, so
    # the check doesn't send this week's again.
    op.execute("UPDATE ingestion_runs SET alerts_sent_at = finished_at WHERE status = 'success'")


def downgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_column("alerts_sent_at")
