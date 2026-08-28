"""Worker profile bodies."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ServiceRequestStatus, WorkerVerificationStatus


class WorkerServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_id: uuid.UUID
    skill_verified: bool


class WorkerServicesUpdate(BaseModel):
    """The trades a worker says they do. Admin verification still gates work."""

    service_ids: Annotated[list[uuid.UUID], Field(max_length=20)]


class ServiceRequestCreate(BaseModel):
    service_id: uuid.UUID
    note: Annotated[str | None, Field(default=None, max_length=1000)]


class ServiceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    service_name: str | None = None
    status: ServiceRequestStatus
    note: str | None
    decision_note: str | None
    decided_at: datetime | None
    created_at: datetime
    # Admin queue only; the worker already knows who they are.
    worker_user_id: uuid.UUID | None = None
    worker_name: str | None = None
    worker_phone: str | None = None


class ServiceRequestDecision(BaseModel):
    approve: bool
    note: Annotated[str | None, Field(default=None, max_length=1000)]


class WorkerProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    bio: str | None
    experience_years: int
    verification_status: WorkerVerificationStatus
    verification_note: str | None
    police_verified: bool
    is_available: bool
    rating_avg: Decimal
    rating_count: int
    jobs_completed: int
    services: list[WorkerServiceRead]
    # True once verification freezes the trade list. Computed server-side so
    # the UI cannot drift from the rule the API actually enforces.
    services_locked: bool = False


class WorkerProfileUpdate(BaseModel):
    bio: Annotated[str | None, Field(default=None, max_length=1000)]
    experience_years: Annotated[int | None, Field(default=None, ge=0, le=60)]
    is_available: bool | None = None


class WorkerSummary(BaseModel):
    """Row in the admin's worker list / assignment picker."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str | None
    phone: str
    verification_status: WorkerVerificationStatus
    is_available: bool
    rating_avg: Decimal
    rating_count: int
    jobs_completed: int
    service_names: list[str] = []
