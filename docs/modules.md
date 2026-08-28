# Module plan

Built one at a time. Each module ships with migrations, tests, and docs before
the next one starts.

---

## ✅ Module 1 — Foundation & identity

Repo layout, Docker stack, config, structured logging, error envelope, rate
limiting. Phone-OTP auth, admin password login, JWT access tokens, rotating
refresh tokens with reuse detection, RBAC for Customer/Worker/Admin.

**Tables:** `users`, `refresh_tokens`
**Endpoints:** `/health/{live,ready}`, `/auth/{request-otp,verify-otp,admin/login,refresh,logout,logout-all}`, `/users/me`

---

## Module 2 — Geography & service catalog

Cities and service zones (Kathmandu first), service categories, the five MVP
services, and fixed transparent pricing. Public browse endpoints plus admin
CRUD.

Pricing is a versioned table, not a column: when a rate changes, past bookings
must still show what the customer actually agreed to pay.

**Tables:** `cities`, `zones`, `service_categories`, `services`, `service_packages`, `price_versions`

---

## Module 3 — Customer profiles & worker onboarding

Customer addresses. Worker profiles, document upload (citizenship, KYC, skill
certificates), the admin verification workflow, and availability management.
Uploads go to local disk behind a storage interface.

This is where the trust differentiator gets built, so verification state is an
explicit state machine — `pending → under_review → verified | rejected` — not a
boolean.

**Tables:** `customer_addresses`, `worker_profiles`, `worker_documents`, `worker_services`, `worker_availability`

---

## Module 4 — Booking lifecycle & dispatch

Quote, create, assign, and the full status machine through completion. Manual
admin dispatch first; automatic matching once there are enough workers for the
choice to matter.

**Tables:** `bookings`, `booking_items`, `booking_status_history`, `assignments`

---

## Module 5 — Payments & invoices

Cash first, because that is how most of Kathmandu will actually pay at launch.
Then eSewa, Khalti and Fonepay. Commission (15–20%) calculated per booking,
worker earnings ledger, digital invoices.

**Tables:** `payments`, `invoices`, `commission_records`, `worker_earnings`, `payouts`

---

## Module 6 — Next.js web & admin dashboard

Marketing site, customer booking flow, and the admin dashboard: worker
verification queue, dispatch board, refunds, analytics.

---

## Module 7 — Flutter apps

Customer and worker apps against the same API.

---

## Later

Notifications (Firebase), live tracking (Maps), reviews and ratings, warranties,
coupons, referrals, loyalty, Nepali localisation, CI/CD and production deploy.
