"""Customer address bodies."""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AddressCreate(BaseModel):
    city_id: uuid.UUID
    label: Annotated[str, Field(default="Home", max_length=40)]
    area: Annotated[str, Field(min_length=2, max_length=120, examples=["Baluwatar"])]
    street: Annotated[str | None, Field(default=None, max_length=200)]
    landmark: Annotated[
        str | None, Field(default=None, max_length=200, examples=["Opposite Chinese Embassy"])
    ]
    directions: str | None = None
    contact_name: Annotated[str | None, Field(default=None, max_length=120)]
    contact_phone: Annotated[str | None, Field(default=None, max_length=20)]
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_default: bool = False


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    area: str
    street: str | None
    landmark: str | None
    directions: str | None
    contact_name: str | None
    contact_phone: str | None
    is_default: bool
    one_line: str
