"""Email-client-friendly SOS message with matching plain-text content."""
from datetime import timezone
from html import escape
from pathlib import Path
from string import Template

TEMPLATE = Path(__file__).with_name("email_templates") / "sos_location.html"


def render_location_email(name, location):
    latitude, longitude = f"{location.latitude:.6f}", f"{location.longitude:.6f}"
    maps_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    timestamp = location.captured_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M:%S UTC")
    accuracy = f"Estimated GPS accuracy: {location.accuracy_meters:.0f} meters." if location.accuracy_meters is not None else ""
    accuracy_html = (
        '<p style="margin:12px 0 0;color:#655C76;font-size:12px;line-height:20px;">'
        + escape(accuracy) + '</p>'
    ) if accuracy else ""
    html = Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        name=escape(name), latitude=latitude, longitude=longitude,
        maps_link=escape(maps_link, quote=True), timestamp=escape(timestamp),
        accuracy_html=accuracy_html,
    )
    text = (
        "SORA SOS — Location shared\n\n"
        f"{name} shared their current location with you. You’re their saved emergency contact.\n"
        "Please contact them to check in.\n\n"
        f"Google Maps: {maps_link}\nCoordinates: {latitude},{longitude}\n"
        f"Captured at: {timestamp}\n" + (accuracy + "\n" if accuracy else "")
        + "\nThis is a GPS snapshot; the sender may have moved since sharing it.\n"
        "This email does not notify emergency services."
    )
    return html, text
