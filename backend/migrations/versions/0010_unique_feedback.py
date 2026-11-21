"""Keep one current rating per answer; preserve the most recent legacy submission."""
from alembic import op
import sqlalchemy as sa

revision = "0010_unique_feedback"
down_revision = "0009_enrichment_retry"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        DELETE FROM answer_feedback WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY question_id ORDER BY created_at DESC, id DESC
                ) AS position FROM answer_feedback
            ) AS ranked WHERE position > 1
        )
    """))
    op.create_index("uq_answer_feedback_question", "answer_feedback", ["question_id"], unique=True)


def downgrade():
    op.drop_index("uq_answer_feedback_question", table_name="answer_feedback")
