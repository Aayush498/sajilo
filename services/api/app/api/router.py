"""v1 router. Each module appends its own router here."""

from fastapi import APIRouter

from app.api.v1 import addresses, admin, auth, bookings, catalog, health, users, worker

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(catalog.router)
api_router.include_router(addresses.router)
api_router.include_router(bookings.router)
api_router.include_router(worker.router)
api_router.include_router(admin.router)
