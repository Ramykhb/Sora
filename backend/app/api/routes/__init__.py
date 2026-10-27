from fastapi import APIRouter, Depends
from app.core.auth import current_user, owned_session
from app.api.routes import dashboard, frames, live, questions, sessions, speech

router = APIRouter(dependencies=[Depends(current_user)])
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(
    frames.router,
    prefix="/sessions/{session_id}/frames",
    tags=["frames"],
    dependencies=[Depends(owned_session)],
)
router.include_router(
    questions.router,
    prefix="/sessions/{session_id}/questions",
    tags=["questions"],
    dependencies=[Depends(owned_session)],
)
router.include_router(
    live.router,
    prefix="/sessions/{session_id}/stream",
    tags=["streaming"],
    dependencies=[Depends(owned_session)],
)
router.include_router(speech.router, prefix="/speech", tags=["speech"])
router.include_router(dashboard.router, tags=["dashboard"])
