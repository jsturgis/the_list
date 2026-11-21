"""fold two Venues made from typos on the List into the Venues they are

"924 Gilman Street, S.F." (Steve's city is wrong: Gilman is in Berkeley) made a second 924 Gilman Street in San
Francisco, and "arp  5 mon Iceage ..." (a misspelt month, read as more of the listing above) made a Venue named
"the Great American Music Hall, S.F. arp 5 mon Iceage at the Independent". Ingest now reads both right
(app/scheduler._stored_at_place, app/ingestion/parser._listing_start), but the stored Gilman copy would still
match its listings by name. Their Shows move to the real Venues, where the next ingest finds them, and the copies
go. Matched by name and city, as made, so a database without them is left alone.

Revision ID: b2d4f6a8c0e1
Revises: a9c1e3f5b7d2
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, None] = "a9c1e3f5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (the copy's name, its city) -> (the real Venue's name, its city)
_FOLDS = [
    (("924 Gilman Street", "San Francisco"), ("924 Gilman Street", "Berkeley")),
    (("the Great American Music Hall, S.F. arp 5 mon Iceage at the Independent", "San Francisco"),
     ("Great American Music Hall", "San Francisco")),
]


def upgrade() -> None:
    conn = op.get_bind()
    for (name, city), (real_name, real_city) in _FOLDS:
        copy = conn.execute(sa.text("SELECT id FROM venues WHERE name = :n AND city = :c AND google_place_id IS NULL"),
                            {"n": name, "c": city}).scalar()
        real = conn.execute(sa.text("SELECT id FROM venues WHERE name = :n AND city = :c ORDER BY id"),
                            {"n": real_name, "c": real_city}).scalar()
        if copy is None or real is None or copy == real:
            continue
        conn.execute(sa.text("UPDATE shows SET venue_id = :real WHERE venue_id = :copy"), {"real": real, "copy": copy})
        conn.execute(sa.text("DELETE FROM venues WHERE id = :copy"), {"copy": copy})


def downgrade() -> None:
    pass  # the copies were mistakes
