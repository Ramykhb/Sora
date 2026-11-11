"""Account-owned destinations with user-defined nicknames and coordinates."""
from alembic import op
import sqlalchemy as sa

revision = "0007_saved_destinations"
down_revision = "0006_place_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_destinations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nickname", sa.String(80), nullable=False),
        sa.Column("nickname_key", sa.String(240), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "nickname_key", name="uq_saved_destination_owner_nickname"),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_destination_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_destination_longitude"),
    )
    op.create_index("ix_saved_destinations_owner_id", "saved_destinations", ["owner_id"])


def downgrade():
    op.drop_table("saved_destinations")
