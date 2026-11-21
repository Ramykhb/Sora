"""Durable bounded enrichment retries and idle backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0009_enrichment_retry"
down_revision = "0008_detection_watches"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stored_frames", sa.Column("enrichment_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("stored_frames", sa.Column("enrichment_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE stored_frames SET enrichment_retry_at = CURRENT_TIMESTAMP "
                       "WHERE enrichment_status = 'skipped' AND "
                       "CAST(processing_warnings AS TEXT) LIKE '%enrichment_superseded%'"))


def downgrade():
    op.drop_column("stored_frames", "enrichment_retry_at")
    op.drop_column("stored_frames", "enrichment_attempts")
