"""ingestion runs record the List page they read, not an email: edition_date and edition_title in place of
email_received_at and email_subject, source_hash (the page's SHA-256) in place of email_message_id, and no more
stats for Band data taken from the formatted edition

Runs that found no edition ("no_email") are deleted: the status is gone, as the page always has the List.

Revision ID: b7d1f3a5c9e2
Revises: e6f8a0b2c4d7
Create Date: 2026-11-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d1f3a5c9e2"
down_revision: Union[str, None] = "e6f8a0b2c4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EDITION_PCTS = ("new_bands_photo_from_edition_pct", "new_bands_genres_from_edition_pct",
                 "new_bands_links_from_edition_pct")


def upgrade() -> None:
    op.execute("DELETE FROM ingestion_runs WHERE status = 'no_email'")
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("edition_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("source_hash", sa.String(length=64), nullable=True))
        batch.alter_column("email_subject", new_column_name="edition_title")
    # email_received_at held the edition's date at midnight; email_message_id was a Drive file id, not a page hash.
    op.execute("UPDATE ingestion_runs SET edition_date = substr(email_received_at, 1, 10)")
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_column("email_received_at")
        batch.drop_column("email_message_id")
        for column in _EDITION_PCTS:
            batch.drop_column(column)


def downgrade() -> None:
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("email_received_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("email_message_id", sa.String(length=200), nullable=True))
        batch.alter_column("edition_title", new_column_name="email_subject")
        for column in _EDITION_PCTS:
            batch.add_column(sa.Column(column, sa.Float(), nullable=True))
    op.execute("UPDATE ingestion_runs SET email_received_at = edition_date || ' 00:00:00.000000'")
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_column("edition_date")
        batch.drop_column("source_hash")
