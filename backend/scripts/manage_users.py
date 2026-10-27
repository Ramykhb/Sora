"""Trusted local administration; passwords are prompted, never command-line arguments."""

import argparse
import asyncio
from getpass import getpass
from uuid import UUID
from sqlalchemy import select, update
from app.auth_schemas import Registration
from app.db.auth_models import User
from app.db.models import CaptureSession
from app.db.session import SessionFactory, engine
from app.services.authentication import hash_password


async def run(args):
    try:
        async with SessionFactory() as db:
            user = await db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if args.command == "create-admin":
                if user:
                    raise ValueError("Account already exists; use promote instead")
                password = getpass("Password (12–128 characters): ")
                if password != getpass("Confirm password: "):
                    raise ValueError("Passwords do not match")
                body = Registration(email=args.email, password=password, display_name=args.name)
                user = User(
                    email=body.email,
                    display_name=body.display_name,
                    password_hash=await hash_password(password),
                    role="admin",
                    email_verified=True,
                )
                db.add(user)
            elif not user:
                raise ValueError("Account not found")
            elif args.command == "promote":
                user.role = "admin"
            elif args.command == "claim-session":
                result = await db.execute(
                    update(CaptureSession)
                    .where(CaptureSession.id == args.session_id, CaptureSession.owner_id.is_(None))
                    .values(owner_id=user.id)
                )
                if result.rowcount != 1:
                    raise ValueError("Session not found or already owned")
            await db.commit()
            print(f"{args.command} completed for {user.email}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin")
    create.add_argument("email")
    create.add_argument("--name", default="Administrator")
    promote = sub.add_parser("promote")
    promote.add_argument("email")
    claim = sub.add_parser("claim-session")
    claim.add_argument("email")
    claim.add_argument("session_id", type=UUID)
    asyncio.run(run(parser.parse_args()))
