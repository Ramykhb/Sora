"""Create local configuration without replacing existing credentials."""

import argparse
from ipaddress import IPv4Address
from pathlib import Path
import secrets

PROJECT = Path(__file__).resolve().parents[2]


def values(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#"))


def configure(project, host):
    path = project / "backend" / ".env"
    template = (project / "backend" / ".env.example").read_text()
    existing = path.read_text() if path.exists() else ""
    current = values(existing)
    defaults = values(template)
    for key in ["POSTGRES_PASSWORD", "S3_SECRET_KEY", "TURN_SHARED_SECRET"]:
        value = current.get(key)
        if not value or value == "GENERATE_LOCAL_SECRET":
            current.pop(key, None)
            value = secrets.token_urlsafe(32)
        defaults[key] = value
    if "GENERATE_LOCAL_SECRET" in current.get("DATABASE_URL", ""):
        current.pop("DATABASE_URL")
    user = current.get("POSTGRES_USER", defaults["POSTGRES_USER"])
    database = current.get("POSTGRES_DB", defaults["POSTGRES_DB"])
    from urllib.parse import quote

    defaults["DATABASE_URL"] = f"postgresql+asyncpg://{quote(user, safe='')}:{quote(defaults['POSTGRES_PASSWORD'], safe='')}@localhost:5432/{database}"
    # Existing credentials and other custom settings always win. A supplied LAN
    # address explicitly updates only networking in the backend and phone config.
    merged = {**defaults, **current}
    merged["TURN_PUBLIC_HOST"] = str(host)
    path.write_text("# Local configuration; do not commit this file.\n" + "".join(f"{key}={value}\n" for key, value in merged.items()))
    path.chmod(0o600)
    mobile = project / "mobile" / ".env.local"
    mobile_values = values(mobile.read_text()) if mobile.exists() else {}
    mobile_values["EXPO_PUBLIC_API_URL"] = f"http://{host}:8000"
    mobile.write_text("".join(f"{key}={value}\n" for key, value in mobile_values.items()))
    return path, mobile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=IPv4Address, required=True, help="Computer IPv4 address reachable from the phone")
    args = parser.parse_args()
    for output in configure(PROJECT, args.host):
        print("Configured:", output)
    print("Recreate API/TURN after a network change. In the installed app, use Change server to update its saved address.")
