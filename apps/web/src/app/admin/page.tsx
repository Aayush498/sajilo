"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type AdminStats,
  type Booking,
  type WorkerSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { npr, when } from "@/lib/format";
import { ErrorNote, Field, Spinner, StatusBadge } from "@/components/ui";

type Tab = "dispatch" | "workers";

export default function AdminPage() {
  const { user, ready, adminLogin } = useAuth();
  const [tab, setTab] = useState<Tab>("dispatch");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [workers, setWorkers] = useState<WorkerSummary[] | null>(null);
  const [candidates, setCandidates] = useState<Record<string, WorkerSummary[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin";

  const load = useCallback(async () => {
    if (!isAdmin) return;
    const [s, b, w] = await Promise.all([
      api.get<AdminStats>("/admin/stats"),
      api.get<Booking[]>("/admin/bookings"),
      api.get<WorkerSummary[]>("/admin/workers"),
    ]);
    setStats(s);
    setBookings(b);
    setWorkers(w);
  }, [isAdmin]);

  useEffect(() => {
    load().catch(() => setBookings([]));
  }, [load]);

  useEffect(() => {
    if (!isAdmin) return;
    const t = setInterval(() => load().catch(() => undefined), 8000);
    return () => clearInterval(t);
  }, [isAdmin, load]);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  /** Loaded on demand — the candidate list is only interesting once you open a job. */
  async function loadCandidates(bookingId: string) {
    if (candidates[bookingId]) return;
    const rows = await api.get<WorkerSummary[]>(`/admin/bookings/${bookingId}/candidates`);
    setCandidates((c) => ({ ...c, [bookingId]: rows }));
  }

  if (!ready) return <Spinner />;
  if (!isAdmin) return <AdminLogin onSubmit={adminLogin} signedInAs={user?.role} />;

  const pending = (bookings ?? []).filter((b) => b.status === "pending");
  const live = (bookings ?? []).filter((b) =>
    ["assigned", "accepted", "en_route", "in_progress", "completed"].includes(b.status),
  );
  const done = (bookings ?? []).filter((b) => ["closed", "cancelled"].includes(b.status));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black">Operations</h1>
        <p className="muted mt-1 text-sm">Live dispatch board · refreshes every 8 seconds</p>
      </div>

      {stats && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Tile label="Bookings" value={String(stats.total_bookings)} />
          <Tile label="Unassigned" value={String(stats.bookings_by_status.pending ?? 0)} warn />
          <Tile label="Gross value" value={npr(stats.gross_booking_value)} />
          <Tile label="Our commission" value={npr(stats.commission_revenue)} highlight />
          <Tile label="Customers" value={String(stats.customers)} />
        </div>
      )}

      {error && <ErrorNote message={error} />}

      <div className="flex gap-1">
        {(["dispatch", "workers"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold capitalize transition-colors ${
              tab === t
                ? "bg-brand-600 text-white"
                : "hover:bg-brand-50 dark:hover:bg-brand-900/30"
            }`}
          >
            {t}
            {t === "workers" && stats && stats.workers_pending_verification > 0 && (
              <span className="ml-2 rounded-full bg-amber-400 px-1.5 text-xs text-amber-950">
                {stats.workers_pending_verification}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === "dispatch" ? (
        bookings === null ? (
          <Spinner />
        ) : (
          <div className="space-y-6">
            <Group
              title="Waiting for a professional"
              hint="Workers can take these themselves, or you can dispatch one now."
              rows={pending}
              busy={busy}
              candidates={candidates}
              onOpen={loadCandidates}
              onAssign={(b, workerId) =>
                run(`assign:${b.id}`, () =>
                  api.post(`/admin/bookings/${b.id}/assign`, { worker_id: workerId }),
                )
              }
              onCancel={(b) =>
                run(`cancel:${b.id}`, () =>
                  api.post(`/admin/bookings/${b.id}/cancel`, { reason: "Cancelled by Sajilo ops" }),
                )
              }
            />
            <Group title="In progress" rows={live} busy={busy} />
            <Group title="Finished" rows={done} busy={busy} collapsed />
          </div>
        )
      ) : workers === null ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {workers.map((w) => (
            <div key={w.user_id} className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-bold">{w.full_name ?? "Unnamed worker"}</p>
                  <p className="muted text-sm">{w.phone}</p>
                  <p className="muted mt-1 text-xs">
                    {w.service_names.length ? w.service_names.join(" · ") : "No trades picked yet"}
                  </p>
                </div>
                <div className="text-right text-sm">
                  <VerificationBadge status={w.verification_status} />
                  <p className="muted mt-1 text-xs">
                    {w.jobs_completed} jobs
                    {w.rating_count > 0 && ` · ★ ${Number(w.rating_avg).toFixed(1)}`}
                  </p>
                </div>
              </div>
              <div
                className="mt-4 flex flex-wrap gap-2 border-t pt-4"
                style={{ borderColor: "var(--border)" }}
              >
                {w.verification_status !== "verified" ? (
                  <button
                    className="btn-primary text-xs"
                    disabled={busy !== null || w.service_names.length === 0}
                    title={
                      w.service_names.length === 0
                        ? "This worker has not picked any trades yet"
                        : undefined
                    }
                    onClick={() =>
                      run(`verify:${w.user_id}`, () =>
                        api.post(`/admin/workers/${w.user_id}/verify?decision=verified`),
                      )
                    }
                  >
                    {busy === `verify:${w.user_id}` ? "Approving…" : "Approve"}
                  </button>
                ) : (
                  <button
                    className="btn-ghost text-xs"
                    disabled={busy !== null}
                    onClick={() =>
                      run(`verify:${w.user_id}`, () =>
                        api.post(`/admin/workers/${w.user_id}/verify?decision=rejected`),
                      )
                    }
                  >
                    Revoke verification
                  </button>
                )}
                <span className="muted self-center text-xs">
                  {w.is_available ? "Available" : "Not taking jobs"}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------- */

function Group({
  title,
  hint,
  rows,
  busy,
  candidates,
  onOpen,
  onAssign,
  onCancel,
  collapsed,
}: {
  title: string;
  hint?: string;
  rows: Booking[];
  busy: string | null;
  candidates?: Record<string, WorkerSummary[]>;
  onOpen?: (id: string) => void;
  onAssign?: (b: Booking, workerId: string) => void;
  onCancel?: (b: Booking) => void;
  collapsed?: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [show, setShow] = useState(!collapsed);

  return (
    <section>
      <button
        className="flex items-baseline gap-2 text-left"
        onClick={() => collapsed && setShow((s) => !s)}
      >
        <h2 className="text-lg font-bold">{title}</h2>
        <span className="muted text-sm">({rows.length})</span>
        {collapsed && <span className="muted text-xs">{show ? "hide" : "show"}</span>}
      </button>
      {hint && <p className="muted mb-3 text-sm">{hint}</p>}

      {show && rows.length === 0 && <p className="muted mt-2 text-sm">Nothing here.</p>}

      {show && (
        <div className="mt-3 space-y-2">
          {rows.map((b) => (
            <div key={b.id} className="card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold">
                    {b.service_name} — {b.package_name}
                  </p>
                  <p className="muted font-mono text-xs">{b.reference}</p>
                  <p className="muted mt-1 text-xs">
                    {b.customer?.full_name ?? "—"} · {b.address?.one_line} · {when(b.scheduled_at)}
                  </p>
                </div>
                <div className="text-right">
                  <StatusBadge status={b.status} />
                  <p className="mt-1.5 text-sm font-bold">{npr(b.total_amount)}</p>
                  {b.commission_amount && (
                    <p className="muted text-xs">we keep {npr(b.commission_amount)}</p>
                  )}
                </div>
              </div>

              {b.worker?.full_name && (
                <p className="muted mt-2 text-xs">👤 {b.worker.full_name}</p>
              )}

              {onAssign && (
                <div
                  className="mt-3 flex flex-wrap gap-2 border-t pt-3"
                  style={{ borderColor: "var(--border)" }}
                >
                  <button
                    className="btn-ghost text-xs"
                    onClick={() => {
                      const next = openId === b.id ? null : b.id;
                      setOpenId(next);
                      if (next) onOpen?.(b.id);
                    }}
                  >
                    {openId === b.id ? "Hide" : "Dispatch a worker"}
                  </button>
                  {onCancel && (
                    <button
                      className="btn-ghost text-xs"
                      disabled={busy !== null}
                      onClick={() => onCancel(b)}
                    >
                      {busy === `cancel:${b.id}` ? "Cancelling…" : "Cancel"}
                    </button>
                  )}
                </div>
              )}

              {openId === b.id && (
                <div className="mt-3 space-y-2">
                  {(candidates?.[b.id] ?? []).length === 0 ? (
                    <p className="muted text-xs">
                      No verified, available worker is cleared for {b.service_name}.
                    </p>
                  ) : (
                    (candidates?.[b.id] ?? []).map((w) => (
                      <div
                        key={w.user_id}
                        className="flex items-center justify-between rounded-lg px-3 py-2 text-sm"
                        style={{ background: "var(--surface-muted)" }}
                      >
                        <div>
                          <p className="font-medium">{w.full_name}</p>
                          <p className="muted text-xs">
                            {w.jobs_completed} jobs
                            {w.rating_count > 0 && ` · ★ ${Number(w.rating_avg).toFixed(1)}`}
                          </p>
                        </div>
                        <button
                          className="btn-primary text-xs"
                          disabled={busy !== null}
                          onClick={() => onAssign?.(b, w.user_id)}
                        >
                          {busy === `assign:${b.id}` ? "Assigning…" : "Assign"}
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function VerificationBadge({ status }: { status: string }) {
  const tone: Record<string, string> = {
    verified: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
    pending: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
    under_review: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
    rejected: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${tone[status] ?? ""}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function Tile({
  label,
  value,
  highlight,
  warn,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  warn?: boolean;
}) {
  return (
    <div
      className={`card p-4 ${highlight ? "border-brand-400 dark:border-brand-600" : ""} ${
        warn && value !== "0" ? "border-amber-400" : ""
      }`}
    >
      <p className="muted text-xs font-semibold uppercase tracking-wide">{label}</p>
      <p
        className={`mt-1 text-xl font-black ${highlight ? "text-brand-600 dark:text-brand-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

function AdminLogin({
  onSubmit,
  signedInAs,
}: {
  onSubmit: (email: string, password: string) => Promise<unknown>;
  signedInAs?: string;
}) {
  const [email, setEmail] = useState("admin@sajilo.com.np");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="card mx-auto max-w-sm space-y-4 p-6"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await onSubmit(email, password);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Could not sign in.");
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <h1 className="text-2xl font-black">Admin sign in</h1>
        {signedInAs && (
          <p className="muted mt-1 text-sm">
            You are signed in as a {signedInAs}. Admin needs its own account.
          </p>
        )}
      </div>

      <Field label="Email">
        <input
          className="input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>
      <Field label="Password">
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>

      {error && <ErrorNote message={error} />}

      <button className="btn-primary w-full" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
