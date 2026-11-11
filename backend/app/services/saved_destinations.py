from sqlalchemy import select

from app.core.errors import BackendError
from app.db.models import SavedDestination
from app.db.session import SessionFactory
from app.destination_schemas import destination_key
from app.schemas import QuestionLocation
from app.services.ai import directions


async def find_destination(owner_id, nickname):
    if owner_id is None:
        return None
    key = destination_key(nickname)
    async with SessionFactory() as db:
        # Prefer an exact nickname; "my home" can also address a saved "home".
        for candidate in dict.fromkeys([key, key.removeprefix("my ")]):
            row = await db.scalar(select(SavedDestination).where(
                SavedDestination.owner_id == owner_id, SavedDestination.nickname_key == candidate,
            ))
            if row is not None:
                return row
    return None


def missing_destination(nickname, language):
    answer = {
        "en": f'There is no saved destination named "{nickname}". Add its nickname and coordinates in Settings first.',
        "fr": f'Aucune destination enregistrée ne porte le nom « {nickname} ». Ajoutez son nom et ses coordonnées dans Réglages.',
        "ar": f'لا توجد وجهة محفوظة باسم «{nickname}». أضف اسمها وإحداثياتها في الإعدادات أولاً.',
    }[language]
    return answer, True, [], ["saved_destination_not_found"]


async def answer_saved(request, destination, language, place_context):
    if request.location is None:
        answer = {
            "en": "Enable location access so I can calculate walking directions from your current position.",
            "fr": "Activez la localisation pour calculer l’itinéraire piéton depuis votre position actuelle.",
            "ar": "فعّل الوصول إلى الموقع لحساب اتجاهات المشي من موقعك الحالي.",
        }[language]
        return answer, True, [], ["location_required"]
    location = QuestionLocation(latitude=destination.latitude, longitude=destination.longitude)
    place_context.update(name=destination.nickname, location=location.model_dump(), place_id=None)
    try:
        route = await directions.walking_route(request.location, location, language)
        return directions.describe_route(route, destination.nickname, language), False, [], []
    except BackendError as exc:
        return directions.MESSAGES[exc.code][language], True, [], [exc.code]
