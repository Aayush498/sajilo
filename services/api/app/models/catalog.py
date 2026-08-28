"""Service catalog: where we operate, what we sell, and what it costs."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class City(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A city we serve. Kathmandu at launch; the rest ship behind is_active."""

    __tablename__ = "cities"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name_ne: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ServiceCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name_ne: Mapped[str | None] = mapped_column(String(80), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    services: Mapped[list["Service"]] = relationship(back_populates="category", lazy="selectin")


class Service(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A bookable service, e.g. House Cleaning."""

    __tablename__ = "services"

    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name_ne: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Commission taken on each completed booking, as a fraction (0.18 = 18%).
    # Per-service because margins differ: cleaning sustains more than AC repair.
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.180")
    )

    # Days of free re-service if the customer is unhappy. 0 = no warranty.
    warranty_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[ServiceCategory] = relationship(back_populates="services", lazy="joined")
    packages: Mapped[list["ServicePackage"]] = relationship(
        back_populates="service", lazy="selectin", order_by="ServicePackage.display_order"
    )


class ServicePackage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A fixed-price option within a service, e.g. "2 BHK Full Cleaning".

    Fixed transparent pricing is the promise, so the customer picks a package
    and sees the exact rupee figure before booking. The price is copied onto
    the booking at creation — changing it here never rewrites history.
    """

    __tablename__ = "service_packages"

    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ne: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    service: Mapped[Service] = relationship(back_populates="packages", lazy="joined")

    __table_args__ = (Index("ix_service_packages_service_id", "service_id"),)
