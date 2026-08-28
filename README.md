# Sajilo — Trusted Home Services

A verified home-services marketplace for Nepal. Launching in Kathmandu, expanding to
Lalitpur, Bhaktapur, Pokhara, Bharatpur, Biratnagar and Butwal.

MVP services: **House Cleaning · Electrician · Plumber · Carpenter · AC Repair**

---

## Quick start

Docker is the only prerequisite.

```powershell
.\dev.ps1 up
```

That builds everything, migrates, seeds the catalogue and demo accounts, then prints
the URLs. Roughly two minutes on a cold cache.

| | |
|---|---|
| Web app | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Without dev.ps1

```bash
cp .env.example .env          # then set SECRET_KEY
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli seed-admin
docker compose exec api python -m app.cli seed-catalog
docker compose exec api python -m app.cli seed-demo
```

### Signing in

**No SMS is sent.** The OTP is printed to the API logs, and outside production it also
comes back as `debug_code` from `/auth/request-otp` — the web app fills it in for you,
so signing in is two clicks.

| Role | Credentials |
|---|---|
| Customer | `9841000100` (Anjali Maharjan) |
| Worker | `9841000001` – `9841000004` (see the login dialog) |
| Admin | `admin@sajilo.com.np` / `ChangeMeNow123!` |

Any other valid Nepali mobile number signs you up as a new user — numbers are validated
against libphonenumber, so `984…`, `986…`, `980…` work and invented ranges do not.

---

## Walking the whole MVP

Open three browser profiles (or one normal and two private windows) so three sessions
can be signed in at once.

**1 · Customer places an order** — http://localhost:3000
Pick a service → pick a package → sign in with `9841000100` → choose the saved address →
confirm. The order lands in **My orders** as *Finding a professional*.

**2 · Worker takes it** — http://localhost:3000/worker
Sign in with `9841000001`. The job is already in **Open jobs** with the payout shown.
Press **Accept this job** — the customer's order flips to *Confirmed* within five seconds,
and both sides can now see each other's phone number.

Then walk it out: **On my way** → **Start work** → **Mark complete + collect cash**.

**3 · Customer rates it** — the order page shows a star rating once the job is complete.
Rating closes the booking and updates the worker's average.

**4 · Admin watches it all** — http://localhost:3000/admin
Live dispatch board, commission revenue, and worker approvals.

### Signing up a brand-new worker

A new worker is **pending verification** and sees nothing. The full path is:

1. Sign in at `/worker` with any unused mobile number, enter a name.
2. Pick the trades they work in.
3. An admin approves them at `/admin` → **Workers** → **Approve**.
4. Open jobs for those trades now appear, and they can take one.

That gate is the product: only a verified worker, cleared for that specific trade and
marked available, can ever be attached to a job.

---

## How it fits together

```
sajilo/
├── services/api/            FastAPI backend (modular monolith)
│   ├── app/models/          SQLAlchemy models + the booking state machine
│   ├── app/services/        Domain logic: auth, OTP, pricing, dispatch
│   └── app/api/v1/          Routes, grouped by audience
├── apps/web/                Next.js 15 — customer, worker portal, admin board
├── docs/                    Architecture and module plan
└── docker-compose.yml       postgres · redis · api · web
```

### The booking lifecycle

```
                    ┌──────── worker claims it ────────┐
                    │                                  ▼
pending ──assign──> assigned ──accept──> accepted ──> en_route ──> in_progress
   │                    │                    │            │             │
   │                  reject                 └────────────┴─────► completed
   │                    │                                              │
   └──────────── cancel ┴──────────────► cancelled              review │
                                                                       ▼
                                                                    closed
```

Every legal move lives in one table (`BOOKING_TRANSITIONS` in
[app/models/enums.py](services/api/app/models/enums.py)) and every move is checked
against it, so an illegal jump is impossible rather than merely unlikely. Each
transition appends to an append-only audit trail — every dispute starts by reading it.

### Two ways a worker gets a job

- **Self-serve** — verified workers see a pool of open jobs for their trades and take
  one. The row is locked before its status is read, so two workers pressing Accept at
  the same instant produce one winner and one clean "already taken", never a double
  booking.
- **Dispatch** — an admin assigns a specific worker, who then accepts or declines.
  A decline returns the job to the pool.

### Money

Prices are fixed per package and snapshotted onto the booking at creation, so changing
the price list never rewrites what a customer already agreed to. Commission is derived
per service; the payout is computed by subtraction so commission + payout always equals
the total exactly, with no rounding drift. Customers are shown the price and never our
cut of it — that filtering happens server-side in `serialize()`, not in the UI.

---

## Commands

```powershell
.\dev.ps1 up        # build, start, migrate, seed
.\dev.ps1 logs      # follow everything (OTP codes appear here)
.\dev.ps1 test      # backend test suite
.\dev.ps1 lint      # ruff + tsc
.\dev.ps1 seed      # re-seed admin, catalog and demo data
.\dev.ps1 psql      # psql shell
.\dev.ps1 down      # stop
.\dev.ps1 reset     # destroy volumes and rebuild from scratch
```

## Tests

```powershell
.\dev.ps1 test
```

Tests run against the real Postgres and Redis in a separate database (`sajilo_test`)
and Redis DB 15, so they never touch your dev data. There is no SQLite substitute — the
schema relies on Postgres partial indexes, native enums and `SELECT … FOR UPDATE`, and
testing against a different engine would not prove much.

## Running the API without Docker

```bash
cd services/api
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

You still need Postgres and Redis reachable at the URLs in `.env`.

## Status

| # | Module | Status |
|---|--------|--------|
| 1 | Foundation, identity & auth (RBAC, OTP, JWT, sessions) | ✅ |
| 2 | Geography & service catalog (cities, zones, fixed pricing) | ✅ |
| 3 | Customer addresses; worker onboarding, trades & verification | ✅ |
| 4 | Booking lifecycle, self-serve claim and admin dispatch | ✅ |
| 5 | Web app: customer, worker portal, admin board | ✅ |
| 6 | Online payments (eSewa, Khalti, Fonepay) and invoices | ⬜ |
| 7 | Push notifications and live worker location | ⬜ |
| 8 | Flutter customer & worker apps | ⬜ |

Cash on completion is the only payment method today; the `payments` table and the
`PaymentMethod` enum already carry the shape the gateways will need.

See [docs/modules.md](docs/modules.md) for the full plan and
[docs/architecture.md](docs/architecture.md) for design decisions.
