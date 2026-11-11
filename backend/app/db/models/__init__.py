from app.db.models.frame import (
    Alert,
    CaptureSession,
    Feedback,
    Frame,
    ObjectDeletion,
    QuestionAnswer,
)

from app.db.models.destination import SavedDestination

__all__ = ["Alert", "CaptureSession", "Feedback", "Frame", "ObjectDeletion", "QuestionAnswer", "SavedDestination"]

# Register identity tables with the shared metadata and Alembic.
from app.db import auth_models as auth_models  # noqa: E402
