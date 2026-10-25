from app.core.config import settings
from app.services.frames.processing import PreparedImage


def rejection_reason(image: PreparedImage, previous_hash: str | None, force: bool = False):
    if force:
        return None
    if image.brightness < settings.min_brightness:
        return "too_dark"
    if image.sharpness < settings.min_sharpness:
        return "too_blurry"
    if (
        previous_hash
        and (int(previous_hash, 16) ^ int(image.perceptual_hash, 16)).bit_count()
        <= settings.duplicate_hash_distance
    ):
        return "duplicate"
    return None
