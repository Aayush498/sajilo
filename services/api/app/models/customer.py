"""Customer-side records."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CustomerAddress(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A saved service location.

    Kathmandu addresses are landmark-based, not street-numbered — "Baluwatar,
    opposite the Chinese Embassy" is how people actually give directions. So
    `landmark` matters as much as `area`, and coordinates are optional until
    maps are wired up.
    """

    __tablename__ = "customer_addresses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    city_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cities.id", ondelete="RESTRICT"), nullable=False
    )

    label: Mapped[str] = mapped_column(String(40), nullable=False, default="Home")
    area: Mapped[str] = mapped_column(String(120), nullable=False)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)
    directions: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_customer_addresses_user_id", "user_id"),)

    @property
    def one_line(self) -> str:
        parts = [self.area, self.street, self.landmark]
        return ", ".join(p for p in parts if p)
