# Module plan

Built one at a time. Each module ships with migrations, tests and docs before
the next one starts.

**This file records what was actually built, not what was originally planned.**
Where the two diverged, the divergence is written down — a plan that quietly
becomes fiction is worse than no plan.

---

## ✅ Module 1 — Foundation & identity

Repo layout, Docker stack, config, structured logging, error envelope, rate
limiting. Phone-OTP auth, admin password login, JWT access tokens, rotating
refresh tokens with reuse detection, RBAC for Customer / Worker / Admin.

**Tables:** `users`, `refresh_tokens`
**Endpoints:** `/health/{live,ready}` · `/auth/{request-otp,verify-otp,admin/login,refresh,logout,logout-all}` · `/users/me`

---

## ✅ Module 2 — Geography & service catalog

Cities, service categories, the five MVP services, and 21 fixed-price packages.
Public browse endpoints, no authentication — asking someone to register before
they can see a price loses most of them.

**Tables:** `cities`, `service_categories`, `services`, `service_packages`
**Endpoints:** `/catalog/{cities,categories,services,services/{slug}}`

### Changed from the plan: no `price_versions` table

The plan was a versioned price table so that past bookings kept their agreed
price. The implementation gets the same guarantee more cheaply: **the booking
snapshots its own price** — service name, package name, unit price, total,
commission rate and payout are all copied onto the `bookings` row at creation.

That is strictly better here. A version table answers "what did this package
cost on 3 August", which nothing in the product asks. A snapshot answers "what
did *this customer* agree to and what was *this worker* promised", which is the
question every invoice and every dispute actually asks — and it survives a
package being deleted outright.

`zones` was also dropped. One city, and addresses carry an area string; zones
buy nothing until dispatch is automatic and needs geographic batching.

---

## ✅ Module 3 — Customer addresses & worker onboarding

Customer addresses with soft delete. Worker profiles, self-selected trades, the
admin verification workflow, and availability.

Verification is an explicit state machine — `pending → under_review →
verified | rejected` — not a boolean, because trust is the product. Only a
`verified` **and** `available` worker who is **cleared for that specific trade**
can be attached to a job, by any route.

**Tables:** `customer_addresses`, `worker_profiles`, `worker_services`, `worker_service_requests`
**Endpoints:** `/addresses` · `/worker/{profile,services,service-requests}` · `/admin/{workers,service-requests}`

### Trades are frozen at verification

A worker picks their trades freely while onboarding. The moment support
verifies them, the list locks — they cannot add one and cannot drop one.

What an admin approved was this person doing *these* trades. If the list stayed
editable, someone verified as a cleaner could tick "Electrician" and start
taking electrical work in a stranger's home; the verification record would
still say approved while meaning nothing.

Widening it goes back through support as a request. Approval writes the
clearance in the same transaction as the decision, so the worker's job pool
widens the moment support says yes — no second step for anyone to forget. A
rejection carries a reason the worker is shown, and does not bar them from
re-applying: the uniqueness index covers *pending* rows only.

### Not built yet: document upload

`worker_documents` and the citizenship / KYC / skill-certificate uploads are
**not implemented**. Admins verify on evidence gathered outside the system
today. The state machine and the `police_verified` and `citizenship_number`
columns are in place, so uploads slot in without a schema rethink — but the
README and product copy should not claim document upload until they exist.

`worker_availability` was dropped in favour of a single `is_available` flag.
Per-day scheduling windows are a real need at scale and pure overhead at four
workers.

---

## ✅ Module 4 — Booking lifecycle & dispatch

Quote, create, and the full status machine through to a rated close.

Every legal move lives in one table, `BOOKING_TRANSITIONS` in
`app/models/enums.py`, and every move is checked against it. An illegal jump is
therefore impossible rather than merely unlikely.

**Two dispatch paths**, both gated on the same eligibility rules:

- **Self-serve** — a verified worker sees a pool of open jobs matching their
  trades and claims one. The row is locked with `SELECT … FOR UPDATE` before
  its status is read, so simultaneous claims produce one winner and one clean
  `409`, never a double booking.
- **Admin dispatch** — staff assign a specific worker, who accepts or declines.
  A decline returns the job to the pool and detaches the worker.

**Tables:** `bookings`, `booking_status_history`, `reviews`
**Endpoints:** `/bookings/*` · `/worker/{jobs,available-jobs,earnings}` · `/admin/bookings/*`

### Changed from the plan

- **No `assignments` table.** A booking has at most one worker at a time, so
  `bookings.worker_id` plus the audit trail carries everything an assignments
  table would. Re-assignment history is already in `booking_status_history`.
- **No `booking_items` table.** Every booking is one package with a quantity.
  A line-items table is the right shape for multi-service baskets, which the
  MVP does not have and may never need.
- **Self-serve claiming was not in the original plan** and became the primary
  path. Manual dispatch alone means nothing happens until a human is watching
  the board.

---

## 🟡 Module 5 — Payments & invoices

**Cash only.** A `payments` row is created with every booking and marked paid
when the worker confirms they collected. Commission and payout are computed and
frozen at booking time.

**Tables:** `payments`
**Not built:** `invoices`, `commission_records`, `worker_earnings`, `payouts`

Online payment — eSewa, Khalti, Fonepay — is not implemented. `PaymentMethod`
already enumerates them and `payments` carries `transaction_id` and `paid_at`,
so a gateway is a new branch rather than a migration.

Worker earnings are computed on read by summing completed bookings
(`/worker/earnings`). That is correct and fast enough at this size; it becomes a
ledger when payouts are real money moving on a schedule rather than cash in
hand.

---

## ✅ Module 6 — Next.js web & admin dashboard

Marketing home, customer booking flow, live order tracking, worker portal,
admin dispatch board, and a shared account page.

- **Customer** — browse, book, track live, rate.
- **Worker** — trade selection, verification state, claimable job pool, the job
  through to completion, earnings.
- **Admin** — live dispatch board, skill-matched candidate lists, one-click
  verification, commission revenue.
- **Everyone** — `/account` for name, email, language and sessions.

Reliability work that turned out to matter more than any feature:

- The client refreshes access tokens silently and retries. Without it every
  user was signed out 15 minutes in, mid-booking. Concurrent expiries share one
  in-flight refresh, because the API rotates refresh tokens and treats reuse as
  theft.
- Error, not-found and loading boundaries, so Next.js never shows a customer
  its stack trace.
- Polling pauses on hidden tabs.
- Radix dialogs, so modals have focus trapping, Escape and scroll locking.

**Not built:** refunds, analytics beyond headline numbers.

---

## ⬜ Module 7 — Flutter apps

Customer and worker apps against the same API. Not started.

---

## ⬜ Later

Notifications (Firebase), live tracking (Maps), warranties as a tracked claim
rather than a promise, coupons, referrals, loyalty, Nepali localisation
(the `locale` column and `name_ne` fields exist; nothing reads them yet),
CI/CD and production deploy.

---

## Honest status

| Area | State |
|---|---|
| Auth, RBAC, sessions | Production-shaped |
| Catalogue & pricing | Production-shaped |
| Booking lifecycle & dispatch | Production-shaped |
| Worker verification | **Workflow only — no document upload** |
| Trade lock & requests | Production-shaped |
| Payments | **Cash only — no gateway** |
| Web app | Production-shaped |
| Notifications | **None.** Status changes are discovered by polling |
| Mobile apps | Not started |
| CI/CD | **None.** Tests are run by hand |
| Nepali localisation | Data seeded, nothing renders it |
