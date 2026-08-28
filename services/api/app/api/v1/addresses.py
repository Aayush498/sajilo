"""Saved service locations for the signed-in customer."""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.models.catalog import City
from app.models.customer import CustomerAddress
from app.schemas.address import AddressCreate, AddressRead

router = APIRouter(prefix="/addresses", tags=["addresses"])


async def _clear_other_defaults(db: DbSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(CustomerAddress)
        .where(CustomerAddress.user_id == user_id, CustomerAddress.is_default.is_(True))
        .values(is_default=False)
    )


@router.get("", response_model=list[AddressRead], summary="My saved addresses")
async def list_addresses(user: CurrentUser, db: DbSession) -> list[CustomerAddress]:
    stmt = (
        select(CustomerAddress)
        .where(CustomerAddress.user_id == user.id, CustomerAddress.is_deleted.is_(False))
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.created_at)
    )
    return list((await db.scalars(stmt)).all())


@router.post(
    "", response_model=AddressRead, status_code=status.HTTP_201_CREATED, summary="Add an address"
)
async def create_address(body: AddressCreate, user: CurrentUser, db: DbSession) -> CustomerAddress:
    city = await db.get(City, body.city_id)
    if city is None or not city.is_active:
        raise NotFoundError("We do not serve that city yet.", code="CITY_UNAVAILABLE")

    existing = await db.scalar(
        select(CustomerAddress.id).where(
            CustomerAddress.user_id == user.id, CustomerAddress.is_deleted.is_(False)
        )
    )
    # First address is always the default; there is nothing to choose between.
    make_default = body.is_default or existing is None
    if make_default:
        await _clear_other_defaults(db, user.id)

    address = CustomerAddress(
        **body.model_dump(exclude={"is_default"}), user_id=user.id, is_default=make_default
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove an address")
async def delete_address(address_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    address = await db.get(CustomerAddress, address_id)
    if address is None or address.is_deleted or address.user_id != user.id:
        raise NotFoundError("Address not found.", code="ADDRESS_NOT_FOUND")

    # Soft delete: past bookings still reference this row.
    address.is_deleted = True
    address.is_default = False
    await db.commit()
