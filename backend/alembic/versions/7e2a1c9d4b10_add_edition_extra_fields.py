"""add formatted-edition fields to shows, venues and bands

Revision ID: 7e2a1c9d4b10
Revises: 5b5092d5ef44
Create Date: 2026-09-30

Databases created by the app's create_all() have no alembic_version table; mark them first with
`alembic stamp 5b5092d5ef44`, then `alembic upgrade head`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7e2a1c9d4b10"
down_revision: Union[str, None] = "5b5092d5ef44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SHOW_FLAGS = ("is_matinee", "is_sold_out", "is_benefit")


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        for name in _SHOW_FLAGS:
            batch.add_column(sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("ticket_provider", sa.String(100), nullable=True))
        batch.add_column(sa.Column("benefit_cause", sa.String(255), nullable=True))
        batch.add_column(sa.Column("special_event", sa.String(255), nullable=True))

    with op.batch_alter_table("venues") as batch:
        batch.add_column(sa.Column("neighborhood", sa.String(255), nullable=True))
        batch.add_column(sa.Column("venue_type", sa.String(100), nullable=True))
        batch.add_column(sa.Column("nearest_transit", sa.String(255), nullable=True))
        batch.add_column(sa.Column("instagram", sa.String(100), nullable=True))
        batch.add_column(sa.Column("image_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("default_age_restriction", sa.String(50), nullable=True))
        batch.add_column(sa.Column("is_sober_space", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("is_cash_only", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("membership_required", sa.Boolean(), nullable=True))

    with op.batch_alter_table("bands") as batch:
        batch.add_column(sa.Column("website_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("image_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("is_local", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bands") as batch:
        for name in ("is_local", "image_url", "website_url"):
            batch.drop_column(name)
    with op.batch_alter_table("venues") as batch:
        for name in ("membership_required", "is_cash_only", "is_sober_space", "default_age_restriction",
                     "image_url", "instagram", "nearest_transit", "venue_type", "neighborhood"):
            batch.drop_column(name)
    with op.batch_alter_table("shows") as batch:
        for name in ("special_event", "benefit_cause", "ticket_provider", *_SHOW_FLAGS):
            batch.drop_column(name)
