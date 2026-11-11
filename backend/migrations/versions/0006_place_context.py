"""Retained place destinations for session-scoped follow-up questions."""
from alembic import op
import sqlalchemy as sa

revision = "0006_place_context"
down_revision = "0005_emergency_contact"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("question_answers", sa.Column("place_context", sa.JSON(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column("question_answers", "place_context")
