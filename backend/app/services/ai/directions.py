"""Walking route facts and instructions from Google Routes, without LLM turns."""
import html
import re

import httpx
from pydantic import BaseModel, Field, StrictInt

from app.core.config import settings
from app.core.errors import BackendError


class NavigationInstruction(BaseModel):
    instructions: str = Field(min_length=1, max_length=2000)


class WalkingStep(BaseModel):
    distanceMeters: StrictInt = Field(default=0, ge=0)
    navigationInstruction: NavigationInstruction


class WalkingLeg(BaseModel):
    steps: list[WalkingStep] = Field(min_length=1, max_length=500)


class WalkingRoute(BaseModel):
    distanceMeters: StrictInt = Field(ge=0)
    legs: list[WalkingLeg] = Field(min_length=1, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=20)


MESSAGES = {
    "routes_not_enabled": {
        "en": "Walking directions are not enabled for the server's Google API key. Enable Routes API and allow it on the key.",
        "fr": "Les itinéraires piétons ne sont pas activés pour la clé Google du serveur. Activez Routes API et autorisez-la pour cette clé.",
        "ar": "اتجاهات المشي غير مفعلة لمفتاح Google على الخادم. فعّل Routes API واسمح بها لهذا المفتاح.",
    },
    "routes_unavailable": {
        "en": "I couldn't get walking directions right now. Please try again.",
        "fr": "Je ne peux pas obtenir l’itinéraire piéton pour le moment. Réessayez.",
        "ar": "تعذر الحصول على اتجاهات المشي الآن. حاول مجدداً.",
    },
    "routes_no_results": {
        "en": "Google Maps returned no walking route to this place.",
        "fr": "Google Maps n’a renvoyé aucun itinéraire piéton vers ce lieu.",
        "ar": "لم يعثر Google Maps على مسار مشي إلى هذا المكان.",
    },
}


async def walking_route(origin, destination, language, place_id=None):
    key = settings.google_routes_api_key.get_secret_value() or settings.google_place_api_key.get_secret_value()
    target = {"placeId": place_id} if place_id else {"location": {"latLng": destination.model_dump()}}
    try:
        async with httpx.AsyncClient(timeout=settings.routes_timeout_seconds) as client:
            response = await client.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                headers={"X-Goog-Api-Key": key,
                         "X-Goog-FieldMask": "routes.distanceMeters,routes.legs.steps.distanceMeters,routes.legs.steps.navigationInstruction,routes.warnings"},
                json={"origin": {"location": {"latLng": origin.model_dump()}},
                      "destination": target, "travelMode": "WALK", "units": "METRIC",
                      "languageCode": language, "computeAlternativeRoutes": False},
            )
            if response.status_code in {401, 403}:
                raise BackendError("Walking routes are not enabled", 503, "routes_not_enabled")
            response.raise_for_status()
        routes = response.json().get("routes", [])
        if not routes:
            raise BackendError("No walking route found", 404, "routes_no_results")
        route = WalkingRoute.model_validate(routes[0])
        # A missing instruction cannot silently remove a turn from the route.
        if any(not plain_text(step.navigationInstruction.instructions) for leg in route.legs for step in leg.steps):
            raise ValueError("Empty navigation instruction")
        return route
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise BackendError("Walking directions unavailable", 503, "routes_unavailable") from exc


def plain_text(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", value)).split())


def describe_route(route, name, language):
    amount = f"{route.distanceMeters} m" if route.distanceMeters < 1000 else f"{route.distanceMeters / 1000:.1f} km"
    intro = {
        "en": f"{name} is approximately {amount} away on foot. Walking directions from Google Maps:",
        "fr": f"{name} est à environ {amount} à pied. Itinéraire piéton de Google Maps :",
        "ar": f"يقع {name} على بُعد نحو {amount} سيراً على الأقدام. اتجاهات المشي من Google Maps:",
    }[language]
    steps = []
    for leg in route.legs:
        for step in leg.steps:
            instruction = plain_text(step.navigationInstruction.instructions).rstrip(". ")
            distance = f" ({step.distanceMeters} m)" if step.distanceMeters else ""
            steps.append(f"{len(steps) + 1}. {instruction}{distance}.")
    # Required by Google's walking-route policy; keep it in spoken answers too.
    warning = {
        "en": "Walking routes may be missing sidewalks or pedestrian paths. This is a route overview; it does not track your progress.",
        "fr": "Des trottoirs ou passages piétons peuvent manquer. Cet aperçu ne suit pas votre progression.",
        "ar": "قد تفتقر مسارات المشي إلى أرصفة أو ممرات للمشاة. هذه نظرة عامة ولا تتتبع تقدمك.",
    }[language]
    advisories = " ".join(plain_text(value) for value in route.warnings)
    return "\n".join([intro, *steps, *([advisories] if advisories else []), warning])
