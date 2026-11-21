"""Backfill canonical lexical terms for accent-insensitive historical retrieval."""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "0011_normalized_frame_search"
down_revision = "0010_unique_feedback"
branch_labels = None
depends_on = None


def canonical_terms(text):
    # Keep migration normalization fixed, independent of future application imports.
    normalized = "".join(char for char in unicodedata.normalize("NFKD", (text or "").casefold())
                         if unicodedata.category(char) not in {"Mn", "Cf"})
    terms = {word[:-1] if len(word) > 3 and word.endswith("s") else word
             for word in re.findall(r"\w+", normalized)}
    return " " + " ".join(sorted(terms)) + " "


def upgrade():
    op.add_column("stored_frames", sa.Column("normalized_search_text", sa.Text(), nullable=False, server_default=""))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, search_text FROM stored_frames"))
    while batch := rows.fetchmany(500):
        connection.execute(sa.text("UPDATE stored_frames SET normalized_search_text = :terms WHERE id = :id"),
                           [{"id": row.id, "terms": canonical_terms(row.search_text)} for row in batch])


def downgrade():
    op.drop_column("stored_frames", "normalized_search_text")
