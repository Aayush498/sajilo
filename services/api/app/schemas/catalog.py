"""Public catalog representations."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    name_ne: str | None
    is_active: bool


class ServicePackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ne: str | None
    description: str | None
    price: Decimal
    duration_minutes: int


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    name_ne: str | None
    description: str | None
    image_url: str | None
    warranty_days: int
    packages: list[ServicePackageRead]


class ServiceCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    name_ne: str | None
    icon: str | None
