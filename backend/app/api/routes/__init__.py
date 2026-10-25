from fastapi import APIRouter, Depends
from app.core.auth import require_key
from app.api.routes import dashboard, frames, live, questions, sessions, speech

router = APIRouter(dependencies=[Depends(require_key)])
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(frames.router, prefix="/sessions/{session_id}/frames", tags=["frames"])
router.include_router(
    questions.router, prefix="/sessions/{session_id}/questions", tags=["questions"]
)
router.include_router(live.router, prefix="/sessions/{session_id}/stream", tags=["streaming"])
router.include_router(speech.router, prefix="/speech", tags=["speech"])
router.include_router(dashboard.router, tags=["dashboard"])
