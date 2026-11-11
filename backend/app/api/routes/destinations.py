from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth import current_user
from app.db.auth_models import User
from app.db.models import SavedDestination
from app.db.session import SessionFactory
from app.destination_schemas import DestinationOut, DestinationWrite, destination_key

router = APIRouter()


@router.get("", response_model=list[DestinationOut])
async def list_destinations(user: User = Depends(current_user)):
    async with SessionFactory() as db:
        return list((await db.scalars(select(SavedDestination).where(
            SavedDestination.owner_id == user.id,
        ).order_by(SavedDestination.nickname_key))).all())


@router.post("", response_model=DestinationOut, status_code=201)
async def create_destination(body: DestinationWrite, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        row = SavedDestination(owner_id=user.id, nickname_key=destination_key(body.nickname), **body.model_dump())
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "You already have a destination with this nickname. Choose another nickname or edit it.") from exc
        await db.refresh(row)
        return row


@router.put("/{destination_id}", response_model=DestinationOut)
async def update_destination(destination_id: UUID, body: DestinationWrite, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        row = await db.scalar(select(SavedDestination).where(
            SavedDestination.id == destination_id, SavedDestination.owner_id == user.id,
        ))
        if row is None:
            raise HTTPException(404, "Saved destination not found")
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.nickname_key = destination_key(body.nickname)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "You already have a destination with this nickname. Choose another nickname or edit it.") from exc
        await db.refresh(row)
        return row


@router.delete("/{destination_id}", status_code=204)
async def delete_destination(destination_id: UUID, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        row = await db.scalar(select(SavedDestination).where(
            SavedDestination.id == destination_id, SavedDestination.owner_id == user.id,
        ))
        if row is None:
            raise HTTPException(404, "Saved destination not found")
        await db.delete(row)
        await db.commit()
    return Response(status_code=204)
