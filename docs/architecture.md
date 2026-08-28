# Sajilo — architecture

## Shape of the system

```
Flutter (Customer)   Flutter (Worker)   Next.js (Web + Admin)
         └──────────────────┬──────────────────┘
                      HTTPS / REST
                            │
                     ┌──────▼──────┐
                     │   FastAPI   │   modular monolith
                     │   /api/v1   │
                     └──┬───┬───┬──┘
           ┌────────────┘   │   └────────────┐
      PostgreSQL          Redis         Object storage
   (source of truth)  (OTP, cache,      (KYC docs, images)
                       rate limits,      — local disk for now
                       queues)
```

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
