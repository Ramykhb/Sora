from datetime import datetime, timedelta, timezone
import math
import re
from sqlalchemy import select
from app.core.config import settings
from app.core.errors import BackendError
from app.core.search_text import words
from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.ai.models import models

MEMORY_WORDS = re.compile(
    r"passed|earlier|previous|ago|remember|just saw|pass[ée]|pr[ée]c[ée]dent|tout à l'heure|مررت|السابق|سابق",
    re.I,
)
PAST_BEFORE = re.compile(
    r"(?:\bdid\s+(?:i|we)\s+(?:see|pass|notice)|\b(?:saw|had seen|was|were)|"
    r"\b(?:ai-je|j'ai|avons-nous)\s+(?:vu|pass[ée])|رأيت|شفت)"
    r"[^?.!]{0,80}(?:\bbefore\b|\bavant\b|قبل)", re.I,
)
STOP_WORDS = set("""
what which who did do does i we you my me the a an and or of on in at to from for
is are was were have had can could tell show please see saw visible image images
frame frames scene scenes object objects shape color colour written read text
describe captured clear concise language surroundings detailed detail
earlier previous previously before ago pass passed remember just yesterday today around about between am pm h
last minutes minute mins hours hour five one two three four ten fifteen twenty thirty
qu que quoi qui ai je j nous vous tu vu est sont et le la les un une des du de au
dans il y a ce cet cette ces plus avant hier dernier dernieres dernieres minutes heures entre vers matin soir
quel quelle quels quelles texte ecrit lire forme couleur objet objets
ماذا ما الذي التي هل انا نحن انت رأيت رايت شفت يوجد في من على عن قبل منذ سابق السابق
امس البارحة صورة صور المشهد نص مكتوب دقيقة دقائق دقايق ساعة ساعات خمس خمسة عشر عشرة بين الساعة مساء صباحا
""".split())


def query_terms(question, timed=False):
    terms = words(question) - words(" ".join(STOP_WORDS))
    if timed or re.search(r"minutes?|hours?|دقائق|دقيقة|دقايق|ساعات|ساعة", question, re.I):
        from app.services.ai.time_query import NUMBER_WORDS

        terms -= words(" ".join(NUMBER_WORDS))
        if timed:
            terms -= words("day days jour jours يوم يوما أيام ايام")
        terms = {term for term in terms if not re.fullmatch(r"\d+(?:am|pm|h)?", term)}
    return sorted(terms)[:12]


def resolve_scope(question, scope):
    return ("memory" if MEMORY_WORDS.search(question) or PAST_BEFORE.search(question) else "recent") if scope == "auto" else scope


async def retrieve_frames(session_id, question, scope="auto", since=None, until=None, limit=None,
                          *, target: datetime | None = None):
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
    # Current-view questions need the newest view, not a costly semantic query.
    if scope != "recent":
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
        if target is not None and scope != "recent":
            # The newest 100 rows may all be after the requested moment. Use
            # the existing session/time index to include nearby frames on both sides.
            for comparison, direction in ((Frame.captured_at <= target, True),
                                          (Frame.captured_at >= target, False)):
                nearby = await db.scalars(
                    select(Frame).where(*filters, comparison)
                    .order_by(Frame.captured_at.desc() if direction else Frame.captured_at.asc())
                    .limit(limit * 8)
                )
                candidates.update({str(frame.id): frame for frame in nearby.all()})
        # Include lexical matches beyond the recent window when semantic services are down.
        tokens = query_terms(question, timed=bool(since or until or target))
        if tokens:
            from sqlalchemy import or_

            matches = await db.scalars(
                select(Frame)
                .where(
                    *filters,
                    or_(
                        *(
                            Frame.normalized_search_text.contains(" " + token + " ", autoescape=True)
                            for token in tokens
                        )
                    ),
                )
                .order_by(Frame.captured_at.desc())
                .limit(100)
            )
            candidates.update({str(f.id): f for f in matches})

    def relevance(frame):
        observed_words = words(frame.search_text)
        lexical = sum(token in observed_words for token in tokens) / max(
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
        return cosine, lexical

    def score(frame):
        cosine, lexical = relevance(frame)
        return 0.75 * cosine + 0.25 * lexical

    if scope == "recent":
        return sorted(candidates.values(), key=lambda f: f.captured_at, reverse=True)[:1], warnings, scope
    if tokens:
        had_candidates = bool(candidates)
        candidates = {key: frame for key, frame in candidates.items()
                      if (relevance(frame)[0] >= settings.retrieval_min_similarity
                          or relevance(frame)[1] >= 0.5)}
        if had_candidates and not candidates:
            warnings.append("no_relevant_evidence")
    if target is not None:
        radius = max((until - since).total_seconds() / 2, 1) if since and until else 60

        def timed_score(frame):
            captured = frame.captured_at
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            proximity = max(0, 1 - abs((captured - target).total_seconds()) / radius)
            return (0.6 * proximity + 0.4 * score(frame), frame.captured_at)

        return sorted(candidates.values(), key=timed_score, reverse=True)[:limit], warnings, scope
    ranked = sorted(candidates.values(), key=lambda f: (score(f), f.captured_at), reverse=True)
    return ranked[:limit], warnings, scope
