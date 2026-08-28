"""Test fixtures.

Runs against the real Postgres and Redis from docker-compose — no SQLite
substitute, because the schema depends on Postgres partial indexes and native
enums. Each test gets a fresh schema and a flushed Redis DB (index 15) so tests
cannot leak state into each other or into your dev data.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("POSTGRES_DB", "sajilo_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-not-used-anywhere-real")
os.environ.setdefault("OTP_TEST_NUMBERS", "")

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    redis = get_redis()
    await redis.flushdb()
    yield
    await redis.flushdb()


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


@pytest.fixture
async def admin_user(db: AsyncSession) -> User:
    from app.core.security import hash_password
    from app.models.enums import UserRole

    admin = User(
        phone="+9779800000001",
        phone_verified=True,
        email="admin@sajilo-test.com",
        password_hash=hash_password("AdminPass123!"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def clear_otp_cooldown(phone_e164: str) -> None:
    """Drop the resend cooldown so one test can log in more than once.

    The cooldown is real behaviour we want in production and test elsewhere; it
    is only in the way when a test needs two logins back to back.
    """
    await get_redis().delete(f"otp:cooldown:{phone_e164}")


async def login_with_otp(client: AsyncClient, phone: str, role: str = "customer") -> dict:
    """Helper: full OTP round-trip, returns the AuthSession body."""
    requested = await client.post("/auth/request-otp", json={"phone": phone, "role": role})
    assert requested.status_code == 200, requested.text
    code = requested.json()["debug_code"]

    verified = await client.post(
        "/auth/verify-otp", json={"phone": phone, "code": code, "role": role}
    )
    assert verified.status_code == 200, verified.text
    return verified.json()
