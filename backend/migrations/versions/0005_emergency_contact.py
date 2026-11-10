"""Account-specific SOS recipient."""
from alembic import op
import sqlalchemy as sa

revision = "0005_emergency_contact"
down_revision = "0004_live_alerts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("emergency_contact_email", sa.String(254), nullable=False, server_default=""))


def downgrade():
    op.drop_column("users", "emergency_contact_email")
