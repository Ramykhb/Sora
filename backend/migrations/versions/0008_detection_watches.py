"""Account-owned, one-shot visual alert memories."""
from alembic import op
import sqlalchemy as sa

revision = "0008_detection_watches"
down_revision = "0007_saved_destinations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "detection_watches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("target_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "target_key", name="uq_detection_watch_owner_target"),
    )
    op.create_index("ix_detection_watches_owner_id", "detection_watches", ["owner_id"])


def downgrade():
    op.drop_table("detection_watches")
