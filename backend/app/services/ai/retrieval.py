from datetime import timedelta
import math
import re
from sqlalchemy import select
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.ai.models import models

MEMORY_WORDS = re.compile(
    r"passed|earlier|previous|before|ago|remember|just saw|pass[ée]|pr[ée]c[ée]dent|tout à l'heure|avant|مررت|قبل|السابق|سابق",
    re.I,
)


def resolve_scope(question, scope):
    return ("memory" if MEMORY_WORDS.search(question) else "recent") if scope == "auto" else scope


async def retrieve_frames(session_id, question, scope="auto", since=None, until=None, limit=None):
    scope = resolve_scope(question, scope)
    limit = limit or settings.retrieval_top_k
    if since and until and since > until:
        raise BackendError("since must be before until", 422, "invalid_time_range")
    filters = [Frame.session_id == session_id, Frame.expires_at > now()]
    if since:
        filters.append(Frame.captured_at >= since)
    if until:
        filters.append(Frame.captured_at <= until)
    if scope == "recent":
        filters.append(
            Frame.captured_at >= now() - timedelta(seconds=settings.recent_evidence_seconds)
        )
    warnings, query_vector = [], None
    try:
        query_vector = await models.embed(question, query=True)
    except BackendError as exc:
        warnings.append(exc.code)
    async with SessionFactory() as db:
        recent = list(
            (
                await db.scalars(
                    select(Frame).where(*filters).order_by(Frame.captured_at.desc()).limit(100)
                )
            ).all()
        )
        semantic = []
        if query_vector is not None and db.bind.dialect.name == "postgresql":
            semantic = list(
                (
                    await db.scalars(
                        select(Frame)
                        .where(
                            *filters,
                            Frame.embedding.is_not(None),
                            Frame.embedding_model == settings.embedding_model,
                        )
                        .order_by(Frame.embedding.cosine_distance(query_vector))
                        .limit(limit * 4)
                    )
                ).all()
            )
        candidates = {str(f.id): f for f in [*recent, *semantic]}
        # Include lexical matches beyond the recent window when semantic services are down.
        tokens = re.findall(r"\w+", question.casefold())[:12]
        if tokens:
            from sqlalchemy import or_

            matches = await db.scalars(
                select(Frame)
                .where(
                    *filters,
                    or_(
                        *(
                            Frame.search_text.ilike("%" + token.replace("%", "") + "%")
                            for token in tokens
                        )
                    ),
                )
                .order_by(Frame.captured_at.desc())
                .limit(100)
            )
            candidates.update({str(f.id): f for f in matches})

    def score(frame):
        lexical = sum(token in frame.search_text.casefold() for token in tokens) / max(
            len(tokens), 1
        )
        cosine = 0.0
        if (
            query_vector is not None
            and frame.embedding is not None
            and frame.embedding_model == settings.embedding_model
        ):
            vector = list(frame.embedding)
            denominator = math.sqrt(sum(x * x for x in vector) * sum(x * x for x in query_vector))
            cosine = (
                sum(a * b for a, b in zip(vector, query_vector)) / denominator if denominator else 0
            )
        return 0.75 * cosine + 0.25 * lexical

    ranked = sorted(candidates.values(), key=lambda f: (score(f), f.captured_at), reverse=True)
    return ranked[:limit], warnings, scope
