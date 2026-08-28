"""Operational commands.

python -m app.cli seed-admin              bootstrap admin account
python -m app.cli seed-catalog            cities, services and prices
python -m app.cli seed-demo               verified demo workers + a customer
python -m app.cli revoke-sessions <uuid>  log a user out everywhere
"""

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.catalog import City, Service
from app.models.customer import CustomerAddress
from app.models.enums import UserRole, UserStatus, WorkerVerificationStatus
from app.models.user import User
from app.models.worker import WorkerProfile, WorkerService
from app.services.auth import revoke_all_sessions
from app.services.catalog_seed import seed_catalog
from app.utils.phone import normalize_phone


async def seed_admin() -> None:
    """Create the bootstrap admin. Idempotent — safe to re-run after deploys."""
    phone = normalize_phone(settings.SEED_ADMIN_PHONE)

    async with SessionLocal() as db:
        existing = await db.scalar(
            select(User).where(User.email == settings.SEED_ADMIN_EMAIL, User.role == UserRole.ADMIN)
        )
        if existing:
            print(f"Admin already exists: {existing.email} ({existing.id})")
            return

        admin = User(
            phone=phone,
            phone_verified=True,
            email=settings.SEED_ADMIN_EMAIL,
            password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
            full_name=settings.SEED_ADMIN_NAME,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        db.add(admin)
        await db.commit()

        print(f"Created admin {admin.email} ({admin.id})")
        if settings.SEED_ADMIN_PASSWORD == "ChangeMeNow123!":
            print("WARNING: the default seed password is in use. Change it before deploying.")


async def run_seed_catalog() -> None:
    async with SessionLocal() as db:
        counts = await seed_catalog(db)
    added = ", ".join(f"{v} {k}" for k, v in counts.items())
    print(f"Catalog synced. Newly added: {added or 'nothing (all up to date)'}")


# Demo workers: (name, phone, services they are cleared for, years, bio)
DEMO_WORKERS = [
    (
        "Ram Bahadur Thapa",
        "+9779841000001",
        ["house-cleaning"],
        6,
        "Six years of residential deep cleaning across Kathmandu.",
    ),
    (
        "Sita Gurung",
        "+9779841000002",
        ["house-cleaning"],
        4,
        "Detail-focused cleaner. Kitchens and bathrooms a speciality.",
    ),
    (
        "Bikash Shrestha",
        "+9779841000003",
        ["electrician", "ac-repair"],
        9,
        "Licensed electrician, also handles AC servicing and installation.",
    ),
    (
        "Hari Prasad Adhikari",
        "+9779841000004",
        ["plumber", "carpenter"],
        12,
        "Plumbing and carpentry. Twelve years in the Valley.",
    ),
]


async def seed_demo() -> None:
    """Verified workers and a customer with an address, for local testing.

    Refuses to run in production — these accounts have known phone numbers and
    would be a live security hole.
    """
    if settings.is_production:
        print("Refusing to seed demo data in production.")
        raise SystemExit(1)

    async with SessionLocal() as db:
        services = {s.slug: s for s in (await db.scalars(select(Service))).unique().all()}
        if not services:
            print("Catalog is empty. Run `seed-catalog` first.")
            raise SystemExit(1)

        kathmandu = await db.scalar(select(City).where(City.slug == "kathmandu"))
        if kathmandu is None:
            print("Kathmandu not found. Run `seed-catalog` first.")
            raise SystemExit(1)

        for name, phone, slugs, years, bio in DEMO_WORKERS:
            user = await db.scalar(select(User).where(User.phone == phone))
            if user is None:
                user = User(phone=phone, phone_verified=True, full_name=name, role=UserRole.WORKER)
                db.add(user)
                await db.flush()

            profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
            if profile is None:
                profile = WorkerProfile(user_id=user.id)
                db.add(profile)
                await db.flush()

            profile.city_id = kathmandu.id
            profile.bio = bio
            profile.experience_years = years
            profile.verification_status = WorkerVerificationStatus.VERIFIED
            profile.police_verified = True
            profile.is_available = True

            for slug in slugs:
                service = services[slug]
                link = await db.scalar(
                    select(WorkerService).where(
                        WorkerService.worker_profile_id == profile.id,
                        WorkerService.service_id == service.id,
                    )
                )
                if link is None:
                    db.add(
                        WorkerService(
                            worker_profile_id=profile.id,
                            service_id=service.id,
                            skill_verified=True,
                        )
                    )
            print(f"  worker  {name:26} {phone}  [{', '.join(slugs)}]")

        customer_phone = "+9779841000100"
        customer = await db.scalar(select(User).where(User.phone == customer_phone))
        if customer is None:
            customer = User(
                phone=customer_phone,
                phone_verified=True,
                full_name="Anjali Maharjan",
                role=UserRole.CUSTOMER,
            )
            db.add(customer)
            await db.flush()

        address = await db.scalar(
            select(CustomerAddress).where(CustomerAddress.user_id == customer.id)
        )
        if address is None:
            db.add(
                CustomerAddress(
                    user_id=customer.id,
                    city_id=kathmandu.id,
                    label="Home",
                    area="Baluwatar",
                    street="Ward 4",
                    landmark="Opposite the Chinese Embassy",
                    contact_name="Anjali Maharjan",
                    contact_phone=customer_phone,
                    is_default=True,
                )
            )
        print(f"  customer{'':2}Anjali Maharjan{'':12}{customer_phone}")

        await db.commit()

    print("\nDemo data ready. Log in with any of these numbers — the OTP is printed")
    print("to the API logs and returned as `debug_code` outside production.")


async def revoke_sessions(user_id: str) -> None:
    async with SessionLocal() as db:
        await revoke_all_sessions(db, uuid.UUID(user_id))
        await db.commit()
    print(f"Revoked all sessions for {user_id}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    command, *args = sys.argv[1:]
    if command == "seed-admin":
        asyncio.run(seed_admin())
    elif command == "seed-catalog":
        asyncio.run(run_seed_catalog())
    elif command == "seed-demo":
        asyncio.run(seed_demo())
    elif command == "revoke-sessions" and args:
        asyncio.run(revoke_sessions(args[0]))
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
