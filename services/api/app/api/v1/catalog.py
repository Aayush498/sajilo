"""Public catalog. No authentication — browsing is the top of the funnel."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.models.catalog import City, Service, ServiceCategory
from app.schemas.catalog import CityRead, ServiceCategoryRead, ServiceRead

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/cities", response_model=list[CityRead], summary="Cities we serve")
async def list_cities(db: DbSession, active_only: bool = True) -> list[City]:
    stmt = select(City).order_by(City.display_order)
    if active_only:
        stmt = stmt.where(City.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


@router.get("/categories", response_model=list[ServiceCategoryRead], summary="Service categories")
async def list_categories(db: DbSession) -> list[ServiceCategory]:
    stmt = select(ServiceCategory).order_by(ServiceCategory.display_order)
    return list((await db.scalars(stmt)).unique().all())


@router.get(
    "/services",
    response_model=list[ServiceRead],
    summary="Bookable services with their fixed-price options",
)
async def list_services(db: DbSession, category: str | None = None) -> list[Service]:
    stmt = select(Service).where(Service.is_active.is_(True)).order_by(Service.display_order)
    if category:
        stmt = stmt.join(ServiceCategory).where(ServiceCategory.slug == category)
    return list((await db.scalars(stmt)).unique().all())


@router.get("/services/{slug}", response_model=ServiceRead, summary="One service by slug")
async def get_service(slug: str, db: DbSession) -> Service:
    service = await db.scalar(
        select(Service).where(Service.slug == slug, Service.is_active.is_(True))
    )
    if service is None:
        raise NotFoundError("Service not found.", code="SERVICE_NOT_FOUND")
    return service
