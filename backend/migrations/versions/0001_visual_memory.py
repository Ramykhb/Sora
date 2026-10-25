"""Visual memory, sessions, questions, alerts, feedback and deletion outbox."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001_visual_memory"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "capture_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capture_sessions_expires_at", "capture_sessions", ["expires_at"])
    op.create_table(
        "stored_frames",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("capture_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("original_object_key", sa.String(1024), nullable=False),
        sa.Column("processed_object_key", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sharpness", sa.Float(), nullable=False),
        sa.Column("brightness", sa.Float(), nullable=False),
        sa.Column("perceptual_hash", sa.String(16), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=False),
        sa.Column("detected_objects", sa.JSON(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("scene_flags", sa.JSON(), nullable=False),
        sa.Column("enhancements", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.String(120), nullable=True),
        sa.Column("processing_warnings", sa.JSON(), nullable=False),
        sa.Column("processing_ms", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in [
        ("session_id", ["session_id"]),
        ("captured_at", ["captured_at"]),
        ("expires_at", ["expires_at"]),
        ("session_time", ["session_id", "captured_at"]),
    ]:
        op.create_index("ix_stored_frames_" + name, "stored_frames", columns)
    op.create_index(
        "ix_frame_embedding_hnsw",
        "stored_frames",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "question_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("capture_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("uncertain", sa.Boolean(), nullable=False),
        sa.Column("evidence_frame_ids", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("processing_warnings", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ["session_id", "created_at", "expires_at"]:
        op.create_index("ix_question_answers_" + column, "question_answers", [column])
    op.create_table(
        "frame_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("capture_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "frame_id",
            sa.Uuid(),
            sa.ForeignKey("stored_frames.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ["session_id", "frame_id"]:
        op.create_index("ix_frame_alerts_" + column, "frame_alerts", [column])
    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("question_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_answer_feedback_question_id", "answer_feedback", ["question_id"])
    op.create_table(
        "object_deletions",
        sa.Column("key", sa.String(1024), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(200), nullable=True),
    )


def downgrade():
    for table in [
        "object_deletions",
        "answer_feedback",
        "frame_alerts",
        "question_answers",
        "stored_frames",
        "capture_sessions",
    ]:
        op.drop_table(table)
