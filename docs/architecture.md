# Sajilo — architecture

## Shape of the system

```
  Next.js (Web · Worker portal · Admin)      Flutter apps — not built yet
                     └──────────────┬──────────────┘
                              HTTPS / REST
                                    │
                             ┌──────▼──────┐
                             │   FastAPI   │   modular monolith
                             │   /api/v1   │
                             └──┬───────┬──┘
                   ┌────────────┘       └────────────┐
              PostgreSQL                          Redis
          (source of truth)                (OTP codes, rate limits)
```

Object storage is in the plan for KYC documents and images, but nothing
uploads files today — see `docs/modules.md`.

## Decisions and why

### Modular monolith, not microservices (yet)

One deployable process. Inside it, each domain is an isolated package —
`identity`, `catalog`, `booking`, `payments`, `dispatch` — with its own models,
schemas, services and routes. Packages talk through service functions, never by
importing each other's models.

Running eight containers before the first paying customer would spend the
runway on orchestration instead of product. The package boundary is the seam:
when Kathmandu volume justifies it, a package lifts out into its own service
without rewriting the domain logic.

### Phone-first identity

Nepal is a phone-first market. Most customers and nearly all workers do not
reliably have email. So:

- The primary identity is a phone number, normalised to E.164 (`+9779841234567`).
- Customers and workers log in with an OTP. There is no password.
- Only admins have a password, because they need a login that does not depend
  on someone holding a specific SIM.

Normalisation happens at the schema boundary (`app/utils/phone.py`), so
`9841234567`, `984-123-4567` and `+977 9841234567` all resolve to one account.
Skipping this creates duplicate accounts that are painful to merge later.

### Tokens

| | Access token | Refresh token |
|---|---|---|
| Format | JWT (HS256) | opaque random, 48 bytes |
| Lifetime | 15 min | 30 days (12 hours for admins) |
| Storage | client only | SHA-256 digest in `refresh_tokens` |
| Carries | `sub`, `role`, `sid` | nothing |

The access token is stateless so the hot path needs no database read for
authorisation. The refresh token is a database row, which is what makes "log
out", "log out everywhere" and admin suspension actually work.

**Rotation with reuse detection.** Every refresh mints a new row pointing at
the one it replaced and revokes the old one. Presenting an already-revoked
token means the token leaked, so every session for that user is revoked. Note
that this revocation is committed *before* the 401 is raised — the request
error handler rolls the transaction back otherwise, which would silently undo
it.

`get_current_user` also checks that the token's session (`sid`) is still live.
That costs one indexed lookup and caps the blast radius of a revoked session at
zero instead of the 15-minute access TTL.

### Prices are snapshotted, not versioned

A booking copies the service name, package name, unit price, total, commission
rate and payout onto its own row at creation. It does not point at the live
price list.

The original plan was a `price_versions` table. A version table answers "what
did this package cost last Tuesday", which nothing in the product asks. A
snapshot answers "what did *this customer* agree to, and what was *this worker*
promised" — the question every invoice and every dispute actually asks — and it
survives the package being deleted outright.

Payout is derived by **subtraction** (`total - commission`), never as its own
percentage, so commission and payout always reconcile to the total exactly with
no rounding drift. Rounding is `ROUND_HALF_UP`, because banker's rounding looks
like an error to someone reading an invoice.

### The booking lifecycle is one table, not scattered conditionals

`BOOKING_TRANSITIONS` in `app/models/enums.py` maps each action to the statuses
it may start from and the one it lands on. `transition()` is the only way a
booking's status changes, and it consults that map every time.

This is the difference between an illegal jump being *impossible* and being
*unlikely because everyone remembered the rules*. Adding a stage means editing
one table; there is no second place that needs to agree.

Every transition also appends to `booking_status_history`, which is append-only.
Every dispute starts by reading it.

### Settlement closes a booking; rating does not

`complete` and `close` used to be separate events driven by separate people: the
worker finished the job, and the booking only reached `closed` when the customer
rated it. That made an optional piece of feedback load-bearing. A customer who
never reopened the app left a paid, finished job sitting in `completed`
indefinitely — still on the dispatch board, still reading as unfinished to the
worker who already had the cash in hand.

Completing a job that has been paid for now closes it in the same transaction,
as a real `close` transition with its own history row, so the audit trail still
shows who ended it and why. `completed` is now exactly one thing: finished work
whose money has not changed hands.

The rating became what it always was — feedback. It is asked for after the fact,
it can be declined, and `submit_review` accepts both `completed` and `closed`.
Because closing no longer guards it, `submit_review` checks the status
explicitly; without that an in-progress job could be rated.

### Declaring a trade is the commitment, not approving it

Signing up as a worker ends with one question — what do you do — and the answer
is frozen the moment it is given. `_is_locked` is simply "has any trade", so the
list is editable exactly once, during onboarding, and never again.

It used to lock at verification instead. That left a window in which the thing
being reviewed could change underneath the reviewer: submit as a cleaner, sit in
the queue, switch to electrician before anyone opened the record, and support
would approve a list they never actually read. Locking at declaration closes it.

An empty trade list therefore means one specific thing — onboarding is not
finished — and the client uses it as the gate: a worker with no trades is shown
the question instead of a dashboard. The API refuses an empty submission
outright, so that state cannot be reached deliberately.

Nothing else changes: verification is still what actually unlocks work, and a
worker awaiting review sees their locked trades and a pending banner. Widening
the list goes through support either way.

Changes go back through support (`worker_service_requests`). The approval writes
the `worker_services` row in the same transaction as the decision, so there is
no window where a request reads "approved" while the worker still cannot see
those jobs.

The uniqueness index on that table is partial — `WHERE status = 'pending'` — so
one live request per trade, while a rejected worker can still re-apply. A plain
unique constraint would bar them forever.

Whether the list is frozen is computed server-side and returned as
`services_locked`, so the UI reads the rule rather than re-deriving it and
drifting from what the API actually enforces.

### Contested jobs are locked, not hoped about

Two workers pressing "Accept" on the same job at the same instant is the normal
case in a job pool, not a rare one. `claim_booking()` takes a row lock —
`SELECT … FOR UPDATE` — *before* it reads the booking's status. The second
request waits, then finds the job taken and gets a clean `409`.

Two details that are easy to get wrong:

- The locking query uses `noload("*")`. The model's default eager loads produce
  outer joins, and Postgres refuses `FOR UPDATE` on the nullable side of one.
- The lock is held until the route commits, so the check and the write are one
  atomic step.

### Responses are filtered server-side, per viewer

`serialize()` builds a booking response *for a specific viewer*. Customers never
receive `commission_amount` or `worker_payout` — the fields are absent from the
payload, not hidden by the UI, so developer tools reveal nothing.

Phone numbers are exchanged only while a job is live (assigned through
completed). Before assignment there is nobody to call; after closing, support
should handle it.

Asking for a booking that is not yours returns `404`, not `403`. Confirming
that a record exists is itself a leak.

### OTP in Redis, not Postgres

Codes are short-lived and disposable. Redis gives TTL expiry for free and
`INCR` for an atomic attempt counter; Postgres would need a sweeper job for no
benefit. Losing Redis costs a user one "resend" tap.

Defence in depth on a channel that costs real money per SMS:

| Guard | Limit |
|---|---|
| Resend cooldown | 60 s per phone |
| Requests | 5 per phone / 15 min, 20 per IP / 15 min |
| Daily cap | 10 codes per phone / 24 h |
| Wrong attempts | 5, then the code is burned |
| Reuse | code is deleted on success |

### Error envelope

Every failure returns the same shape:

```json
{"error": {"code": "OTP_INVALID", "message": "...", "details": {}}}
```

Clients branch on `code`, never on `message`. That lets us reword copy — or
translate it to Nepali — without shipping a new app build.

### Soft deletes via partial unique indexes

`uq_users_phone_active` is unique only `WHERE status <> 'deleted'`. A deleted
account keeps its rows for accounting and dispute history, while releasing the
phone number for re-registration. A plain unique constraint would force us to
either scramble the stored number or block the person from ever coming back.

## The web client

### It decides nothing

The Next.js app renders and collects clicks. Every rule — who may do what, what
things cost, which moves are legal — lives in the API and is re-checked on every
request. There is no path from developer tools to a discount, because the
browser was never trusted with the decision in the first place.

### Sessions refresh silently, exactly once at a time

Access tokens last 15 minutes. The client refreshes on a `401` and retries the
original request, so nobody is signed out mid-booking.

The part that is load-bearing: **all concurrent callers await one in-flight
refresh**. The worker portal fires four requests at once. Four independent
refreshes would mean three arriving with an already-rotated token, which the API
correctly treats as theft and answers by revoking the entire session — turning a
refresh into a logout. The single shared promise is what prevents that, and it
is covered by a test that fails if the deduplication regresses.

When a refresh genuinely fails, the client clears its tokens *and* tells React,
so the UI cannot render a signed-in shell that 401s on every action.

### Liveness by polling

Every screen showing something another person can change polls: the order the
customer is watching, their order list, the worker's job pool and the dispatch
board. Server-sent events or websockets would be tidier, but polling needs no
extra infrastructure and a few seconds of lag is invisible for a job that takes
an hour.

The intervals live together in `POLL_MS` in `apps/web/src/lib/format.ts` rather
than as a number typed into each page, so the app's total polling load is
readable in one place — and the dispatch board's "refreshes every N seconds"
caption reads from the same constant, so the copy cannot drift from the timer.

Which statuses count as still-moving is also shared, as `LIVE_STATUSES`. The
order page stops polling once a booking settles. `completed` is in that list
because unpaid work still moves — the worker confirming the cash closes it, and
the customer watching should see that happen.

Polling stops while the tab is hidden and refetches on return. A backgrounded
tab was thousands of pointless requests per user, and browsers throttle those
timers unpredictably anyway, so the data was not fresh either.

### Onboarding gates live above the router

The prompt asking a new user for their name is rendered in the root layout, not
inside the sign-in dialog. Signing in changes the very state that pages branch
on, so a prompt owned by a page can be unmounted mid-flow by the page
underneath it — which is exactly how workers were reaching admin approval with
no name. A gate above the router cannot be torn down that way.

## Local-first, by design

Nothing in the stack requires a paid service today:

| Concern | Now (free, local) | Later |
|---|---|---|
| SMS | logged to console | Sparrow / Aakash SMS |
| Storage | local disk | S3 / DO Spaces |
| Push | — | Firebase |
| Maps | — | Google Maps |

Each of these sits behind a narrow interface (`app/services/sms.py` is the
pattern) so the paid provider arrives as one new branch, not a refactor.

## Conventions

- **Migrations are hand-checked.** Autogenerate drafts them; a human reads the
  diff before it merges. Both `upgrade()` and `downgrade()` must run cleanly.
- **Services hold the logic, routes stay thin.** A route validates, calls a
  service, commits, returns. Business rules live in `app/services/`.
- **Routes own the transaction.** Services `flush()`; the route `commit()`s.
  One request is one transaction.
- **Never log a full phone number.** Use `mask_phone()`.
