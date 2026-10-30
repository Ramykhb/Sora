"""Durable background descriptions for quickly saved live frames."""

from alembic import op
import sqlalchemy as sa

revision = "0003_frame_enrichment"
down_revision = "0002_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "stored_frames",
        sa.Column("enrichment_status", sa.String(20), nullable=False, server_default="complete"),
    )
    op.add_column("stored_frames", sa.Column("enrichment_ms", sa.Float(), nullable=True))
    op.create_index("ix_stored_frames_enrichment_status", "stored_frames", ["enrichment_status"])


def downgrade():
    op.drop_index("ix_stored_frames_enrichment_status", table_name="stored_frames")
    op.drop_column("stored_frames", "enrichment_ms")
    op.drop_column("stored_frames", "enrichment_status")
