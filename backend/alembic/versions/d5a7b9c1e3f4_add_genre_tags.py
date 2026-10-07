"""add genre_tags: whether a tag outside the genre vocabulary is a genre, judged once (app/ingestion/genre_filter.py)

Revision ID: d5a7b9c1e3f4
Revises: c4f6a8b0d2e5
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5a7b9c1e3f4"
down_revision: Union[str, None] = "c4f6a8b0d2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "genre_tags",
        sa.Column("tag", sa.String(), primary_key=True),
        sa.Column("example", sa.String(), nullable=False),
        sa.Column("is_genre", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("genre_tags")
