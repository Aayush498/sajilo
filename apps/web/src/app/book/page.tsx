"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type Address,
  type Booking,
  type City,
  type Service,
  type ServicePackage,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { duration, npr, SERVICE_EMOJI } from "@/lib/format";
import { LoginDialog } from "@/components/LoginDialog";
import { ErrorNote, Field, Spinner } from "@/components/ui";

function BookingFlow() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, ready } = useAuth();

  const [services, setServices] = useState<Service[] | null>(null);
  const [service, setService] = useState<Service | null>(null);
  const [pkg, setPkg] = useState<ServicePackage | null>(null);

  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState<string>("");
  const [showNewAddress, setShowNewAddress] = useState(false);
  const [cities, setCities] = useState<City[]>([]);

  const [instant, setInstant] = useState(true);
  const [scheduledAt, setScheduledAt] = useState("");
  const [notes, setNotes] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [login, setLogin] = useState(false);

  useEffect(() => {
    api.get<Service[]>("/catalog/services", false).then((list) => {
      setServices(list);
      const slug = params.get("service");
      const preselect = slug ? list.find((s) => s.slug === slug) : null;
      if (preselect) setService(preselect);
    });
    api.get<City[]>("/catalog/cities", false).then(setCities);
  }, [params]);

  const loadAddresses = useCallback(async () => {
    if (!user) return;
    const list = await api.get<Address[]>("/addresses");
    setAddresses(list);
    const preferred = list.find((a) => a.is_default) ?? list[0];
    if (preferred) setAddressId(preferred.id);
    setShowNewAddress(list.length === 0);
  }, [user]);

  useEffect(() => {
    loadAddresses().catch(() => undefined);
  }, [loadAddresses]);

  async function submit() {
    if (!pkg || !addressId) return;
    setBusy(true);
    setError(null);
    try {
      const booking = await api.post<Booking>("/bookings", {
        package_id: pkg.id,
        address_id: addressId,
        quantity: 1,
        notes: notes || null,
        scheduled_at: instant ? null : new Date(scheduledAt).toISOString(),
      });
      router.push(`/orders/${booking.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the booking.");
      setBusy(false);
    }
  }

  if (services === null) return <Spinner label="Loading services…" />;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-black">Book a service</h1>
        <p className="muted mt-1 text-sm">Fixed price, shown before you commit.</p>
      </div>

      {/* Step 1 — service */}
      <section className="card p-5">
        <StepHead n={1} title="Choose a service" done={!!service} />
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {services.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setService(s);
                setPkg(null);
              }}
              className={`rounded-xl border p-3 text-left transition-all hover:border-brand-400 ${
                service?.id === s.id
                  ? "border-brand-500 bg-brand-50 dark:bg-brand-900/40"
                  : ""
              }`}
              style={service?.id === s.id ? undefined : { borderColor: "var(--border)" }}
            >
              <span className="text-xl">{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
              <p className="mt-1 text-sm font-semibold">{s.name}</p>
            </button>
          ))}
        </div>
      </section>

      {/* Step 2 — package */}
      {service && (
        <section className="card animate-rise p-5">
          <StepHead n={2} title={`Pick your ${service.name.toLowerCase()} option`} done={!!pkg} />
          <div className="mt-4 space-y-2">
            {service.packages.map((p) => (
              <button
                key={p.id}
                onClick={() => setPkg(p)}
                className={`flex w-full items-center justify-between gap-4 rounded-xl border p-4 text-left transition-all hover:border-brand-400 ${
                  pkg?.id === p.id ? "border-brand-500 bg-brand-50 dark:bg-brand-900/40" : ""
                }`}
                style={pkg?.id === p.id ? undefined : { borderColor: "var(--border)" }}
              >
                <div>
                  <p className="font-semibold">{p.name}</p>
                  <p className="muted text-xs">
                    {p.description} · about {duration(p.duration_minutes)}
                  </p>
                </div>
                <p className="shrink-0 text-lg font-bold">{npr(p.price)}</p>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Step 3 — where and when */}
      {pkg && (
        <section className="card animate-rise p-5">
          <StepHead n={3} title="Where and when" done={!!addressId} />

          {!ready ? (
            <Spinner />
          ) : !user ? (
            <div className="mt-4 rounded-xl bg-brand-50 p-4 text-sm dark:bg-brand-900/30">
              <p className="font-medium">Sign in to continue</p>
              <p className="muted mt-1">We need a number to send your professional to.</p>
              <button className="btn-primary mt-3" onClick={() => setLogin(true)}>
                Sign in
              </button>
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              {addresses.length > 0 && (
                <Field label="Service address">
                  <div className="space-y-2">
                    {addresses.map((a) => (
                      <button
                        key={a.id}
                        onClick={() => setAddressId(a.id)}
                        className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left ${
                          addressId === a.id
                            ? "border-brand-500 bg-brand-50 dark:bg-brand-900/40"
                            : ""
                        }`}
                        style={addressId === a.id ? undefined : { borderColor: "var(--border)" }}
                      >
                        <span className="mt-0.5">📍</span>
                        <span>
                          <span className="block text-sm font-semibold">{a.label}</span>
                          <span className="muted block text-xs">{a.one_line}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </Field>
              )}

              {showNewAddress ? (
                <NewAddressForm
                  cities={cities}
                  onCreated={async () => {
                    setShowNewAddress(false);
                    await loadAddresses();
                  }}
                  onCancel={addresses.length ? () => setShowNewAddress(false) : undefined}
                />
              ) : (
                <button className="btn-ghost text-xs" onClick={() => setShowNewAddress(true)}>
                  + Add a new address
                </button>
              )}

              <Field label="When">
                <div className="flex gap-2">
                  <button
                    className={`btn ${instant ? "btn-primary" : "btn-ghost"} flex-1`}
                    onClick={() => setInstant(true)}
                  >
                    As soon as possible
                  </button>
                  <button
                    className={`btn ${!instant ? "btn-primary" : "btn-ghost"} flex-1`}
                    onClick={() => setInstant(false)}
                  >
                    Schedule
                  </button>
                </div>
                {!instant && (
                  <input
                    type="datetime-local"
                    className="input mt-2"
                    value={scheduledAt}
                    onChange={(e) => setScheduledAt(e.target.value)}
                  />
                )}
              </Field>

              <Field label="Notes for the professional (optional)">
                <textarea
                  className="input min-h-20"
                  placeholder="Gate code, pets, parking, anything they should know…"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </Field>
            </div>
          )}
        </section>
      )}

      {/* Step 4 — confirm */}
      {pkg && user && addressId && (
        <section className="card animate-rise border-brand-300 p-5 dark:border-brand-700">
          <StepHead n={4} title="Confirm and book" done={false} />
          <dl className="mt-4 space-y-2 text-sm">
            <Row k="Service" v={`${service!.name} — ${pkg.name}`} />
            <Row k="Duration" v={`about ${duration(pkg.duration_minutes)}`} />
            <Row k="Warranty" v={`${service!.warranty_days} days`} />
            <Row k="Payment" v="Cash on completion" />
            <div
              className="flex justify-between border-t pt-3 text-lg font-bold"
              style={{ borderColor: "var(--border)" }}
            >
              <dt>Total</dt>
              <dd>{npr(pkg.price)}</dd>
            </div>
          </dl>

          {error && <div className="mt-4">{<ErrorNote message={error} />}</div>}

          <button
            className="btn-primary mt-5 w-full !py-3 text-base"
            disabled={busy || (!instant && !scheduledAt)}
            onClick={submit}
          >
            {busy ? "Creating your booking…" : `Confirm booking · ${npr(pkg.price)}`}
          </button>
          <p className="muted mt-2 text-center text-xs">
            You can cancel free of charge until the professional starts work.
          </p>
        </section>
      )}

      {login && (
        <LoginDialog
          role="customer"
          onClose={() => {
            setLogin(false);
            loadAddresses().catch(() => undefined);
          }}
        />
      )}
    </div>
  );
}

function StepHead({ n, title, done }: { n: number; title: string; done: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs font-bold ${
          done ? "bg-brand-600 text-white" : "bg-slate-200 dark:bg-slate-800"
        }`}
      >
        {done ? "✓" : n}
      </span>
      <h2 className="font-bold">{title}</h2>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <dt className="muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}

function NewAddressForm({
  cities,
  onCreated,
  onCancel,
}: {
  cities: City[];
  onCreated: () => void;
  onCancel?: () => void;
}) {
  const [cityId, setCityId] = useState("");
  const [label, setLabel] = useState("Home");
  const [area, setArea] = useState("");
  const [landmark, setLandmark] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cities.length && !cityId) setCityId(cities[0].id);
  }, [cities, cityId]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.post("/addresses", {
        city_id: cityId,
        label,
        area,
        landmark: landmark || null,
        is_default: true,
      });
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the address.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: "var(--border)" }}>
      <p className="mb-3 text-sm font-semibold">New address</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="City">
          <select className="input" value={cityId} onChange={(e) => setCityId(e.target.value)}>
            {cities.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Label">
          <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Field label="Area / Tole">
          <input
            className="input"
            placeholder="Baluwatar"
            value={area}
            onChange={(e) => setArea(e.target.value)}
          />
        </Field>
        <Field label="Landmark">
          <input
            className="input"
            placeholder="Opposite the Chinese Embassy"
            value={landmark}
            onChange={(e) => setLandmark(e.target.value)}
          />
        </Field>
      </div>
      {error && <div className="mt-3">{<ErrorNote message={error} />}</div>}
      <div className="mt-3 flex gap-2">
        <button className="btn-primary text-xs" disabled={busy || area.length < 2} onClick={save}>
          {busy ? "Saving…" : "Save address"}
        </button>
        {onCancel && (
          <button className="btn-ghost text-xs" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

export default function BookPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <BookingFlow />
    </Suspense>
  );
}
