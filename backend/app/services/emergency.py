"""Explicit user-triggered SOS location sharing through Brevo."""
import httpx

from app.auth_schemas import EmailRequest
from app.core.config import settings
from app.core.errors import BackendError
from app.services.emergency_email import render_location_email


async def send_location_email(user, location):
    if not settings.brevo_api_key.get_secret_value() or not settings.brevo_sender_email:
        raise BackendError("SOS email is not configured. Set BREVO_API_KEY and BREVO_SENDER_EMAIL on the server.", 503, "sos_not_configured")
    try:
        sender = EmailRequest(email=settings.brevo_sender_email).email
    except ValueError as exc:
        raise BackendError("The SOS sender email is invalid", 503, "sos_not_configured") from exc
    html, text = render_location_email(user.display_name, location)
    try:
        async with httpx.AsyncClient(timeout=settings.brevo_timeout_seconds) as client:
            response = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": settings.brevo_api_key.get_secret_value()},
                json={
                    "sender": {"email": sender, "name": settings.brevo_sender_name},
                    "to": [{"email": user.emergency_contact_email}],
                    "subject": "Sora SOS — Location shared",
                    "textContent": text,
                    "htmlContent": html,
                    "headers": {"IdempotencyKey": f"sora-sos-{user.id}-{location.request_id}"},
                },
            )
            response.raise_for_status()
            if not response.json().get("messageId"):
                raise ValueError("No message confirmation")
    except httpx.TimeoutException as exc:
        raise BackendError("The email service timed out; delivery could not be confirmed. Check with your SOS contact before sending again.", 504, "sos_delivery_unknown") from exc
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise BackendError("The SOS email could not be confirmed. Please try again or contact your SOS contact directly.", 503, "sos_email_unavailable") from exc
