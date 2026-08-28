<div align="center">

# सजिलो · Sajilo

### Trusted home services, made easy.

**The verified-professional marketplace for Nepal.**
Fixed prices. KYC-checked people. Work that comes with a warranty.

<br>

![Status](https://img.shields.io/badge/status-MVP%20complete-14806f?style=for-the-badge)
![Tests](https://img.shields.io/badge/tests-46%20passing-1fa189?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.12-14806f?style=for-the-badge&logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/next.js-15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br>

```
🧹  House Cleaning     💡  Electrician     🔧  Plumber     🪚  Carpenter     ❄️  AC Repair
```

**One command to run the entire platform.**

```powershell
.\dev.ps1 up      # PowerShell
./dev.sh up       # Git Bash · WSL · macOS · Linux
```

</div>

---

## The problem

Finding a plumber in Kathmandu is easy. **Trusting one is not.**

You are about to hand a stranger the keys to your home. You do not know if they are
skilled. You do not know if they are safe. And you will not learn the price until they
are already standing in your kitchen, tools out, leverage theirs.

Every home-services transaction in Nepal runs on this asymmetry.

## What Sajilo does about it

<table>
<tr>
<td width="33%" valign="top">

### 🪪 Verified, not claimed

Every professional passes identity and background checks **before their first job**.
Verification is a state machine with an audit trail, not a checkbox somebody ticked.

</td>
<td width="33%" valign="top">

### 🏷️ The price, up front

21 fixed-price packages. You see the exact rupee figure **before** you commit, and it
is frozen onto your booking. No haggling, no "actually it's more".

</td>
<td width="33%" valign="top">

### 🛡️ Backed by warranty

3 to 30 days depending on the trade. Something not right? Somebody comes back and
fixes it. Free.

</td>
</tr>
</table>

---

## Product tour

### For customers — book in under a minute

> Browse without signing up · fixed price shown before you commit · live status that
> updates itself · cash on completion · rate the work when it's done

No password anywhere. Your phone number is your account — one code, and you're in.
Booking is four steps, and the price is on screen from step two.

Once a professional takes your job, the order page starts moving on its own —
**Confirmed → On the way → Work in progress → Completed** — with their name, rating and
phone number appearing the moment they're assigned.

### For professionals — a job board that respects your trade

> Open jobs matched to your trades · payout shown before you accept · one tap to claim ·
> earnings that reconcile to the paisa

You pick the trades you work in. You only ever see jobs for those trades — a plumber is
never shown an AC job, and could not take one if they tried.

Every open job shows **what you take home**, not the customer's price. Accept it and the
job is yours; the customer's screen updates within seconds.

### For operations — a live dispatch board

> Real-time queue · skill-matched candidate lists · one-click verification · commission
> revenue at a glance

Unassigned jobs surface immediately. Open one and you get only workers who are verified,
available, **and** cleared for that exact service — best-rated first. Approve new
professionals in one click.

---

## The engineering that makes it trustworthy

This is the part that matters. A marketplace is only as good as its guarantees.

<table>
<tr><th width="34%">Guarantee</th><th>How it is enforced</th></tr>

<tr><td><b>🔒 Two people can't take the same job</b></td>
<td>Simultaneous accepts are the normal case, not the rare one. The booking row is locked with <code>SELECT … FOR UPDATE</code> <i>before</i> its status is read. One winner, one clean <code>409 JOB_ALREADY_TAKEN</code> — never a double booking. Covered by a concurrency test that fires both requests at once.</td></tr>

<tr><td><b>🚦 Illegal state jumps are impossible</b></td>
<td>Every legal move lives in one table — <code>BOOKING_TRANSITIONS</code> — and every move is checked against it. Not "unlikely because everyone remembered the rules". <i>Impossible.</i> Adding a stage means editing one table.</td></tr>

<tr><td><b>📜 Every dispute has an answer</b></td>
<td>Append-only audit trail. Who did what, when, and why. Never edited, never deleted.</td></tr>

<tr><td><b>🧾 History never rewrites itself</b></td>
<td>Prices are snapshotted onto the booking at creation. Raise the price list tomorrow and every past booking still shows what that customer agreed to and what that worker was promised.</td></tr>

<tr><td><b>💰 Money cannot drift</b></td>
<td>Payout is derived by <i>subtraction</i>, never as its own percentage — so commission + payout equals the total exactly, always. Rounding is half-up, the way an invoice reads to a human.</td></tr>

<tr><td><b>🙈 Customers never see our cut</b></td>
<td>Commission and payout are stripped server-side before the response is sent. Not hidden with CSS — genuinely absent from the payload. DevTools reveals nothing.</td></tr>

<tr><td><b>📵 Phone numbers only while it matters</b></td>
<td>Shared from assignment through completion. Before that there is nobody to call; after, support should handle it.</td></tr>

<tr><td><b>🔑 A revoked session dies in minutes</b></td>
<td>Access tokens last 15 minutes, but every request re-checks the underlying session. Logout, suspension or refresh-token reuse caps the damage window at 15 minutes, not 30 days.</td></tr>

<tr><td><b>🕵️ Enumeration leaks nothing</b></td>
<td>Ask for a booking that isn't yours and you get <code>404</code>, not <code>403</code>. Confirming a record exists is itself a leak.</td></tr>

<tr><td><b>📱 One person, one account</b></td>
<td>Every number is normalised to E.164 and validated against libphonenumber, so <code>9841234567</code>, <code>098-4123-4567</code> and <code>+977 9841234567</code> are the same human — not three.</td></tr>
</table>

---

## Architecture

```
                        ┌─────────────────────────┐
                        │        BROWSER          │
                        └────────────┬────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │   WEB  ·  Next.js 15    │   :3000
                        │   React 19 · Tailwind 4 │
                        │                         │
                        │   Draws screens.        │
                        │   Decides nothing.      │
                        └────────────┬────────────┘
                                     │  HTTP · JSON
                        ┌────────────▼────────────┐
                        │   API  ·  FastAPI       │   :8000
                        │   Python 3.12           │
                        │                         │
                        │   Every rule lives      │
                        │   here. 43 endpoints.   │
                        └───────┬────────┬────────┘
                                │        │
                  ┌─────────────▼──┐  ┌──▼──────────────┐
                  │  POSTGRES 16   │  │    REDIS 7      │
                  │  :5432         │  │    :6379        │
                  │                │  │                 │
                  │  14 tables     │  │  OTP codes      │
                  │  row locking   │  │  rate limits    │
                  │  native enums  │  │  auto-expiring  │
                  └────────────────┘  └─────────────────┘
```

**The web layer is deliberately dumb.** It renders and collects clicks. Every rule —
who may do what, what things cost, which moves are legal — lives in the API and is
re-checked on every request. You cannot give yourself a discount from DevTools, because
the browser was never trusted with the decision.

---

## Under the hood

<table>
<tr><td width="50%" valign="top">

**Backend**
| | |
|---|---|
| Framework | FastAPI |
| Language | Python 3.12 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | PyJWT + Argon2 |
| Phone | libphonenumber |
| Logging | structlog |

</td><td width="50%" valign="top">

**Frontend**
| | |
|---|---|
| Framework | Next.js 15 |
| UI | React 19 |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| Theme | Light + dark, no flash |

**Infrastructure**
| | |
|---|---|
| Runtime | Docker Compose |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Tests | pytest · 46 passing |
| Lint | ruff · tsc |

</td></tr>
</table>

---

## Quick start

**Docker is the only prerequisite.**

```powershell
.\dev.ps1 up      # PowerShell
./dev.sh up       # Git Bash, WSL, macOS, Linux
```

Builds four containers, applies migrations, seeds the catalogue and demo accounts, and
prints your URLs. About two minutes cold.

<table>
<tr><td>🌐 <b>Web app</b></td><td><a href="http://localhost:3000">localhost:3000</a></td></tr>
<tr><td>⚙️ <b>API</b></td><td><a href="http://localhost:8000">localhost:8000</a></td></tr>
<tr><td>📖 <b>Live API docs</b></td><td><a href="http://localhost:8000/docs">localhost:8000/docs</a> — every endpoint, clickable</td></tr>
</table>

### Sign in

**No SMS is sent in development.** The code comes back as `debug_code` and the web app
fills it in for you — signing in is two clicks.

| Role | Credentials |
|---|---|
| 🏠 Customer | `9841000100` — Anjali Maharjan |
| 🔧 Worker | `9841000001` … `9841000004` — listed in the login dialog |
| 🛡️ Admin | `admin@sajilo.com.np` · `ChangeMeNow123!` |

Any unused valid Nepali mobile signs you up fresh.

---

## See the whole thing work

Open **three separate browser contexts** — Chrome incognito windows share storage with
each other, so use e.g. Chrome + Chrome incognito + Edge. Put customer and worker side
by side; that's where it's satisfying.

```
1 · CUSTOMER    localhost:3000 → Book a service → Plumber → Inspection Visit
                sign in 9841000100 → pick address → Confirm
                                                    ↓
                                        status: Finding a professional

2 · WORKER      localhost:3000/worker → sign in 9841000004
                "Open jobs 1" · NPR 656 payout → Accept this job
                                                    ↓
3 · WATCH       the customer's tab flips to Confirmed on its own, within 5s,
                revealing the professional's name, rating and phone number

4 · DELIVER     On my way → Start work → Mark complete + collect cash
                each one lands on the customer's screen in seconds

5 · CLOSE       customer rates it → booking closes → worker's earnings update
```

<details>
<summary><b>Onboarding a brand-new professional — the trust gate</b></summary>

<br>

A new worker is **pending verification** and sees nothing at all:

1. Sign in at `/worker` with any unused mobile → you're asked for your name
2. Pick the trades you work in
3. An admin approves you at `/admin` → **Workers** → **Approve**
4. Open jobs for those trades appear — and only then

That gate *is* the product. Only a verified worker, cleared for that specific trade and
marked available, can ever be attached to a job — through any path, including admin
dispatch.

</details>

<details>
<summary><b>Two ways a job finds a professional</b></summary>

<br>

**Self-serve** — verified workers see a pool of open jobs matching their trades and take
one. Race-safe by row locking.

**Dispatch** — an admin assigns a specific worker, who accepts or declines. A decline
returns the job to the pool and detaches them, so the board doesn't re-offer it.

</details>

<details>
<summary><b>The booking lifecycle</b></summary>

<br>

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

Cancel is allowed up to `en_route`. Once work has started it is not — somebody is
already in the customer's home.

Defined in [`app/models/enums.py`](services/api/app/models/enums.py), enforced in
[`app/services/booking.py`](services/api/app/services/booking.py).

</details>

---

## Repository

```
sajilo/
├── services/api/              FastAPI backend · modular monolith
│   ├── app/models/            Schema + the booking state machine
│   ├── app/services/          Domain logic: auth, OTP, pricing, dispatch
│   ├── app/api/v1/            43 endpoints, grouped by audience
│   └── tests/                 46 tests
│
├── apps/web/                  Next.js 15
│   └── src/app/               Customer · worker portal · admin board · account
│
├── dev.ps1 · dev.sh           Same helper, one per shell
├── docs/                      Architecture and module plan
├── PROJECT_OVERVIEW.txt       Full walkthrough, no prior knowledge assumed
└── docker-compose.yml         postgres · redis · api · web
```

**New here?** Read [`PROJECT_OVERVIEW.txt`](PROJECT_OVERVIEW.txt) — it explains the whole
system from scratch, including a glossary, and assumes nothing.

---

## Commands

Two identical helpers ship with the repo — use whichever matches your shell.
`.\dev.ps1 <cmd>` in PowerShell, `./dev.sh <cmd>` in Git Bash, WSL, macOS or Linux.

| Command | What it does |
|---|---|
| `up` | build, start, migrate, seed |
| `logs` | follow everything — OTP codes appear here |
| `test` | 46 backend tests |
| `lint` | ruff + tsc |
| `seed` | re-seed admin, catalog and demo data |
| `migrate` | apply migrations |
| `psql` | database shell |
| `shell` | bash inside the api container |
| `down` | stop |
| `reset` | destroy volumes and rebuild from scratch |

Prefer raw Docker? Every helper command is a thin wrapper — `docker compose up -d --build`,
`docker compose logs -f`, and so on. Nothing is hidden.

Tests run against real Postgres and Redis in a separate database, never your dev data.
There is no SQLite substitute — the schema depends on native enums, partial indexes and
`SELECT … FOR UPDATE`, and testing against a different engine would not prove much.

---

## Roadmap

| | Milestone | |
|---|---|---|
| 1 | Identity & auth — RBAC, OTP, JWT, sessions | ✅ |
| 2 | Geography & catalogue — cities, fixed pricing | ✅ |
| 3 | Customer addresses · worker onboarding, trades & verification | ✅ |
| 4 | Booking lifecycle — self-serve claim and admin dispatch | ✅ |
| 5 | Web — customer, worker portal, admin board, account | ✅ |
| 6 | Online payments — eSewa · Khalti · Fonepay · invoices | ⬜ |
| 7 | Push notifications · live worker location | ⬜ |
| 8 | Flutter apps — customer & worker | ⬜ |

Cash on completion is the only payment method today. The `payments` table and
`PaymentMethod` enum already carry the shape the gateways will need.

**Launching in Kathmandu.** Lalitpur, Bhaktapur, Pokhara, Bharatpur, Biratnagar and
Butwal are already seeded, switched off until we're ready.

---

<div align="center">

**Sajilo** · Kathmandu, Nepal

*Every professional is KYC and citizenship verified.*

</div>
