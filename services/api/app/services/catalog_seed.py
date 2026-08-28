"""Reference data: the cities we serve and the five MVP services.

Prices are in NPR and reflect typical Kathmandu market rates. They live here
rather than in a migration so they can be corrected without a schema change —
`seed-catalog` is idempotent and updates existing rows in place.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import City, Service, ServiceCategory, ServicePackage

CITIES: list[tuple[str, str, str, bool]] = [
    # (name, slug, nepali name, live at launch)
    ("Kathmandu", "kathmandu", "काठमाडौं", True),
    ("Lalitpur", "lalitpur", "ललितपुर", False),
    ("Bhaktapur", "bhaktapur", "भक्तपुर", False),
    ("Pokhara", "pokhara", "पोखरा", False),
    ("Bharatpur", "bharatpur", "भरतपुर", False),
    ("Biratnagar", "biratnagar", "विराटनगर", False),
    ("Butwal", "butwal", "बुटवल", False),
]

CATEGORIES: list[tuple[str, str, str, str]] = [
    # (name, slug, nepali name, icon)
    ("Cleaning", "cleaning", "सरसफाइ", "sparkles"),
    ("Repairs & Maintenance", "repairs", "मर्मत सम्भार", "wrench"),
]

# (service name, slug, nepali, category slug, commission, warranty days, blurb)
SERVICES: list[tuple[str, str, str, str, str, int, str]] = [
    (
        "House Cleaning",
        "house-cleaning",
        "घर सरसफाइ",
        "cleaning",
        "0.200",
        3,
        "Deep cleaning by trained, background-checked staff. Supplies included.",
    ),
    (
        "Electrician",
        "electrician",
        "इलेक्ट्रिसियन",
        "repairs",
        "0.180",
        15,
        "Licensed electricians for wiring, fittings and fault finding.",
    ),
    (
        "Plumber",
        "plumber",
        "प्लम्बर",
        "repairs",
        "0.180",
        15,
        "Leaks, blockages, taps and fittings — fixed the same day.",
    ),
    (
        "Carpenter",
        "carpenter",
        "सिकर्मी",
        "repairs",
        "0.180",
        30,
        "Furniture repair, fittings and custom woodwork.",
    ),
    (
        "AC Repair",
        "ac-repair",
        "एसी मर्मत",
        "repairs",
        "0.150",
        30,
        "Servicing, gas refill and installation for all major brands.",
    ),
]

# service slug -> [(package name, nepali, price NPR, minutes, blurb)]
PACKAGES: dict[str, list[tuple[str, str, str, int, str]]] = {
    "house-cleaning": [
        ("1 BHK Full Cleaning", "१ बीएचके", "1500.00", 120, "All rooms, kitchen and one bathroom."),
        ("2 BHK Full Cleaning", "२ बीएचके", "2200.00", 180, "All rooms, kitchen and two bathrooms."),
        (
            "3 BHK Full Cleaning",
            "३ बीएचके",
            "3000.00",
            240,
            "All rooms, kitchen and three bathrooms.",
        ),
        (
            "Kitchen Deep Clean",
            "भान्सा सफाइ",
            "1800.00",
            120,
            "Degreasing, cabinets, appliances and floor.",
        ),
        ("Bathroom Deep Clean", "बाथरुम सफाइ", "1200.00", 90, "Tiles, fittings and sanitising."),
    ],
    "electrician": [
        ("Inspection Visit", "निरीक्षण", "800.00", 60, "Diagnosis and minor fixes, up to one hour."),
        ("Fan / Light Installation", "पंखा जडान", "600.00", 45, "Per fitting, wiring included."),
        ("Switchboard Replacement", "स्विचबोर्ड", "1200.00", 90, "Replace and test one board."),
        ("Wiring Repair", "वायरिङ मर्मत", "1500.00", 120, "Fault tracing and rewiring."),
    ],
    "plumber": [
        ("Inspection Visit", "निरीक्षण", "800.00", 60, "Diagnosis and minor fixes, up to one hour."),
        ("Tap / Faucet Repair", "धारा मर्मत", "700.00", 45, "Repair or replace one fitting."),
        ("Pipe Leak Fix", "पाइप लिक", "1200.00", 90, "Locate and seal the leak."),
        ("Toilet Repair", "शौचालय मर्मत", "1500.00", 120, "Flush, seal and fitting work."),
    ],
    "carpenter": [
        ("Inspection Visit", "निरीक्षण", "900.00", 60, "Assessment and minor repairs."),
        ("Door Lock Fitting", "ढोका लक", "1000.00", 60, "Supply excluded, fitting included."),
        ("Furniture Repair", "फर्निचर मर्मत", "1500.00", 120, "Chairs, tables, beds and cabinets."),
        ("Cabinet Installation", "क्याबिनेट जडान", "2500.00", 180, "Wall or floor mounted."),
    ],
    "ac-repair": [
        (
            "AC Service (1 unit)",
            "एसी सर्भिस",
            "1200.00",
            60,
            "Filter clean, coil wash and gas check.",
        ),
        ("AC Deep Clean", "गहिरो सफाइ", "1800.00", 90, "Full strip-down clean of one unit."),
        ("AC Installation", "एसी जडान", "2500.00", 120, "Mounting, piping and testing."),
        ("AC Gas Refill", "ग्यास रिफिल", "3500.00", 90, "Leak test and full refill."),
    ],
}


async def seed_catalog(db: AsyncSession) -> dict[str, int]:
    """Insert or update all reference data. Safe to run on every deploy."""
    counts = {"cities": 0, "categories": 0, "services": 0, "packages": 0}

    for order, (name, slug, name_ne, active) in enumerate(CITIES):
        city = await db.scalar(select(City).where(City.slug == slug))
        if city is None:
            city = City(slug=slug)
            db.add(city)
            counts["cities"] += 1
        city.name, city.name_ne, city.is_active, city.display_order = name, name_ne, active, order

    categories: dict[str, ServiceCategory] = {}
    for order, (name, slug, name_ne, icon) in enumerate(CATEGORIES):
        category = await db.scalar(select(ServiceCategory).where(ServiceCategory.slug == slug))
        if category is None:
            category = ServiceCategory(slug=slug)
            db.add(category)
            counts["categories"] += 1
        category.name, category.name_ne, category.icon, category.display_order = (
            name,
            name_ne,
            icon,
            order,
        )
        categories[slug] = category

    await db.flush()

    for order, (name, slug, name_ne, cat_slug, rate, warranty, blurb) in enumerate(SERVICES):
        service = await db.scalar(select(Service).where(Service.slug == slug))
        if service is None:
            service = Service(slug=slug)
            db.add(service)
            counts["services"] += 1
        service.name = name
        service.name_ne = name_ne
        service.category_id = categories[cat_slug].id
        service.commission_rate = Decimal(rate)
        service.warranty_days = warranty
        service.description = blurb
        service.is_active = True
        service.display_order = order
        await db.flush()

        for pkg_order, (pkg_name, pkg_ne, price, minutes, desc) in enumerate(PACKAGES[slug]):
            package = await db.scalar(
                select(ServicePackage).where(
                    ServicePackage.service_id == service.id, ServicePackage.name == pkg_name
                )
            )
            if package is None:
                package = ServicePackage(service_id=service.id, name=pkg_name)
                db.add(package)
                counts["packages"] += 1
            package.name_ne = pkg_ne
            package.price = Decimal(price)
            package.duration_minutes = minutes
            package.description = desc
            package.is_active = True
            package.display_order = pkg_order

    await db.commit()
    return counts
