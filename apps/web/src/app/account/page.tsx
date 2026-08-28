"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { LogOut, MapPin, ShieldCheck, Trash2, User as UserIcon } from "lucide-react";
import {
  ApiError,
  api,
  type Address,
  type City,
  type Service,
  type WorkerProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { SERVICE_EMOJI } from "@/lib/format";
import { Empty, ErrorNote, Field, Spinner } from "@/components/ui";

export default function AccountPage() {
  const { user, ready, updateProfile, logout, logoutEverywhere } = useAuth();

  const [services, setServices] = useState<Service[]>([]);
  const [profile, setProfile] = useState<WorkerProfile | null>(null);
  const [addresses, setAddresses] = useState<Address[] | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isWorker = user?.role === "worker";
  const isCustomer = user?.role === "customer";

  const load = useCallback(async () => {
    if (!user) return;
    if (isWorker) setProfile(await api.get<WorkerProfile>("/worker/profile"));
    if (isCustomer) setAddresses(await api.get<Address[]>("/addresses"));
  }, [user, isWorker, isCustomer]);

  useEffect(() => {
    if (isWorker) {
      api
        .get<Service[]>("/catalog/services", false)
        .then(setServices)
        .catch(() => setServices([]));
    }
  }, [isWorker]);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function run(key: string, fn: () => Promise<unknown>, okMessage?: string) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await load();
      if (okMessage) toast.success(okMessage);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  if (!ready) return <Spinner />;
  if (!user)
    return (
      <Empty title="Sign in to manage your account" hint="Use the button in the header." />
    );

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-black">Account</h1>
        <p className="muted mt-1 text-sm capitalize">
          {user.role} · {user.phone}
        </p>
      </div>

      {error && <ErrorNote message={error} />}
      <DetailsCard
        user={user}
        busy={busy}
        onSave={(patch) => run("details", () => updateProfile(patch), "Details saved.")}
      />

      {isWorker && profile && (
        <WorkerCard
          profile={profile}
          services={services}
          busy={busy}
          onSaveProfile={(patch) =>
            run("worker", () => api.patch<WorkerProfile>("/worker/profile", patch), "Profile saved.")
          }
          onSaveTrades={(ids) =>
            run("trades", () => api.put<WorkerProfile>("/worker/services", { service_ids: ids }))
          }
        />
      )}

      {isCustomer && (
        <AddressCard
          addresses={addresses}
          busy={busy}
          onDelete={(id) =>
            run(`addr:${id}`, () => api.del(`/addresses/${id}`), "Address removed.")
          }
        />
      )}

      <section className="card p-5">
        <h2 className="flex items-center gap-2 font-bold"><ShieldCheck size={16} /> Sessions</h2>
        <p className="muted mt-0.5 text-sm">
          Signing out everywhere ends every session on every device. Use it if you lose your
          phone.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-ghost text-sm" onClick={logout}>
            <LogOut size={14} />
            Sign out
          </button>
          <button
            className="btn-ghost text-sm"
            disabled={busy !== null}
            onClick={() => run("logout-all", logoutEverywhere)}
          >
            {busy === "logout-all" ? "Signing out…" : "Sign out everywhere"}
          </button>
        </div>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function DetailsCard({
  user,
  busy,
  onSave,
}: {
  user: { full_name: string | null; email: string | null; locale: string };
  busy: string | null;
  onSave: (patch: { full_name?: string; email?: string | null; locale?: string }) => void;
}) {
  const [name, setName] = useState(user.full_name ?? "");
  const [email, setEmail] = useState(user.email ?? "");
  const [locale, setLocale] = useState(user.locale);

  // The saved values arrive after the first render, so mirror them in.
  useEffect(() => {
    setName(user.full_name ?? "");
    setEmail(user.email ?? "");
    setLocale(user.locale);
  }, [user.full_name, user.email, user.locale]);

  const dirty =
    name.trim() !== (user.full_name ?? "") ||
    email.trim() !== (user.email ?? "") ||
    locale !== user.locale;

  return (
    <section className="card p-5">
      <h2 className="flex items-center gap-2 font-bold"><UserIcon size={16} /> Your details</h2>
      <div className="mt-4 space-y-4">
        <Field label="Full name">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>

        <Field label="Email (optional)">
          <input
            className="input"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <p className="muted mt-1.5 text-xs">Used for receipts. Never shown to anyone else.</p>
        </Field>

        <Field label="Language">
          <div className="flex gap-2">
            {[
              ["en", "English"],
              ["ne", "नेपाली"],
            ].map(([code, label]) => (
              <button
                key={code}
                onClick={() => setLocale(code)}
                className={`btn flex-1 ${locale === code ? "btn-primary" : "btn-ghost"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </Field>

        <button
          className="btn-primary"
          disabled={busy !== null || !dirty || name.trim().length < 2}
          onClick={() =>
            onSave({
              full_name: name.trim(),
              // An empty box means "remove it", which is null, not "".
              email: email.trim() === "" ? null : email.trim(),
              locale,
            })
          }
        >
          {busy === "details" ? "Saving…" : "Save changes"}
        </button>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function WorkerCard({
  profile,
  services,
  busy,
  onSaveProfile,
  onSaveTrades,
}: {
  profile: WorkerProfile;
  services: Service[];
  busy: string | null;
  onSaveProfile: (patch: { bio?: string; experience_years?: number; is_available?: boolean }) => void;
  onSaveTrades: (ids: string[]) => void;
}) {
  const [bio, setBio] = useState(profile.bio ?? "");
  const [years, setYears] = useState(String(profile.experience_years));

  useEffect(() => {
    setBio(profile.bio ?? "");
    setYears(String(profile.experience_years));
  }, [profile.bio, profile.experience_years]);

  const trades = new Set(profile.services.map((s) => s.service_id));
  const verified = profile.verification_status === "verified";
  const yearsNum = Number(years);
  const yearsValid = Number.isInteger(yearsNum) && yearsNum >= 0 && yearsNum <= 60;
  const dirty = bio !== (profile.bio ?? "") || yearsNum !== profile.experience_years;

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold">Work profile</h2>
          <p className="muted mt-0.5 text-sm">Customers see this when you take their job.</p>
        </div>
        <span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold capitalize text-brand-700 dark:bg-brand-900/50 dark:text-brand-200">
          {profile.verification_status.replace(/_/g, " ")}
        </span>
      </div>

      <div className="mt-4 space-y-4">
        <Field label="About you">
          <textarea
            className="input min-h-24"
            maxLength={1000}
            placeholder="Six years of residential deep cleaning across Kathmandu."
            value={bio}
            onChange={(e) => setBio(e.target.value)}
          />
          <p className="muted mt-1.5 text-xs">{bio.length}/1000</p>
        </Field>

        <Field label="Years of experience">
          <input
            className="input"
            type="number"
            min={0}
            max={60}
            value={years}
            onChange={(e) => setYears(e.target.value)}
          />
          {!yearsValid && (
            <p className="mt-1.5 text-xs text-rose-600 dark:text-rose-400">
              Enter a whole number between 0 and 60.
            </p>
          )}
        </Field>

        <button
          className="btn-primary"
          disabled={busy !== null || !dirty || !yearsValid}
          onClick={() => onSaveProfile({ bio, experience_years: yearsNum })}
        >
          {busy === "worker" ? "Saving…" : "Save work profile"}
        </button>

        <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="label">Trades you work in</p>
          <p className="muted mb-3 text-xs">
            You only ever see jobs for these. Changes save immediately.
          </p>
          <div className="flex flex-wrap gap-2">
            {services.map((s) => {
              const on = trades.has(s.id);
              return (
                <button
                  key={s.id}
                  disabled={busy !== null}
                  onClick={() => {
                    const current = [...trades];
                    onSaveTrades(
                      on ? current.filter((id) => id !== s.id) : [...current, s.id],
                    );
                  }}
                  className={`rounded-xl border px-3 py-2 text-sm font-medium transition-all disabled:opacity-50 ${
                    on
                      ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200"
                      : "hover:border-brand-400"
                  }`}
                  style={on ? undefined : { borderColor: "var(--border)" }}
                >
                  <span className="mr-1.5">{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
                  {s.name}
                  {on && <span className="ml-1.5">✓</span>}
                </button>
              );
            })}
          </div>
        </div>

        <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-sm">Taking jobs</p>
              <p className="muted text-xs">
                {verified
                  ? "Turn this off and you stop appearing for new jobs."
                  : "Unlocked once Sajilo has verified your account."}
              </p>
            </div>
            <button
              className={profile.is_available && verified ? "btn-primary" : "btn-ghost"}
              disabled={busy !== null || !verified}
              onClick={() => onSaveProfile({ is_available: !profile.is_available })}
            >
              {profile.is_available ? "🟢 Available" : "⚪ Not taking jobs"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function AddressCard({
  addresses,
  busy,
  onDelete,
}: {
  addresses: Address[] | null;
  busy: string | null;
  onDelete: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <section className="card p-5">
      <h2 className="flex items-center gap-2 font-bold"><MapPin size={16} /> Saved addresses</h2>
      <p className="muted mt-0.5 text-sm">Add a new one while booking a service.</p>

      {addresses === null ? (
        <Spinner />
      ) : addresses.length === 0 ? (
        <p className="muted mt-4 text-sm">No saved addresses yet.</p>
      ) : (
        <div className="mt-4 space-y-2">
          {addresses.map((a) => (
            <div
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-sm"
              style={{ background: "var(--surface-muted)" }}
            >
              <div>
                <p className="font-medium">
                  {a.label}
                  {a.is_default && (
                    <span className="ml-2 rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      default
                    </span>
                  )}
                </p>
                <p className="muted text-xs">{a.one_line}</p>
              </div>

              {confirming === a.id ? (
                <div className="flex gap-2">
                  <button
                    className="btn-ghost text-xs text-rose-600 dark:text-rose-400"
                    disabled={busy !== null}
                    onClick={() => {
                      onDelete(a.id);
                      setConfirming(null);
                    }}
                  >
                    <Trash2 size={13} />
                    {busy === `addr:${a.id}` ? "Removing…" : "Yes, remove"}
                  </button>
                  <button className="btn-ghost text-xs" onClick={() => setConfirming(null)}>
                    Keep
                  </button>
                </div>
              ) : (
                <button
                  className="btn-ghost text-xs"
                  disabled={busy !== null}
                  onClick={() => setConfirming(a.id)}
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
