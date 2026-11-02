"""Live obstacle observations do not require a stored memory frame."""

from alembic import op
import sqlalchemy as sa

revision = "0004_live_alerts"
down_revision = "0003_frame_enrichment"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("frame_alerts", "frame_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("frame_alerts", sa.Column(
        "captured_at", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.func.now(),
    ))


def downgrade():
    op.execute("DELETE FROM frame_alerts WHERE frame_id IS NULL")
    op.drop_column("frame_alerts", "captured_at")
    op.alter_column("frame_alerts", "frame_id", existing_type=sa.Uuid(), nullable=False)
