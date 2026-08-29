"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BadgeCheck, Briefcase, Clock, MapPin, Wallet } from "lucide-react";
import {
  ApiError,
  api,
  type Booking,
  type Earnings,
  type Service,
  type ServiceRequest,
  type WorkerProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { POLL_MS, SERVICE_EMOJI, duration, npr, when } from "@/lib/format";
import { LoginDialog } from "@/components/LoginDialog";
import { TradePicker } from "@/components/TradePicker";
import { WorkerOnboarding } from "@/components/WorkerOnboarding";
import { usePolling } from "@/hooks/usePolling";
import { CardSkeleton, Empty, ErrorNote, Spinner, StatusBadge } from "@/components/ui";

/** What the worker can do next, per status. */
const NEXT_ACTION: Record<string, { path: string; label: string }[]> = {
  assigned: [
    { path: "accept", label: "Accept job" },
    { path: "reject", label: "Decline" },
  ],
  accepted: [{ path: "start-travel", label: "On my way" }],
  en_route: [{ path: "start", label: "Start work" }],
  in_progress: [{ path: "complete", label: "Mark complete + collect cash" }],
};

const VERIFICATION_COPY: Record<string, { tone: string; title: string; body: string }> = {
  pending: {
    tone: "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
    title: "Waiting for Sajilo to verify you",
    body: "Your trades are locked in and your account is with our team for review. Sajilo checks every professional before their first job — open jobs appear here the moment you are approved.",
  },
  under_review: {
    tone: "bg-sky-50 text-sky-900 dark:bg-sky-500/10 dark:text-sky-200",
    title: "Verification in progress",
    body: "We are checking your documents. This usually takes a day.",
  },
  rejected: {
    tone: "bg-rose-50 text-rose-900 dark:bg-rose-500/10 dark:text-rose-200",
    title: "Verification was not approved",
    body: "Contact Sajilo support to find out what is missing.",
  },
};

export default function WorkerPage() {
  const { user, ready } = useAuth();
  const [profile, setProfile] = useState<WorkerProfile | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [jobs, setJobs] = useState<Booking[] | null>(null);
  const [open, setOpen] = useState<Booking[]>([]);
  const [earnings, setEarnings] = useState<Earnings | null>(null);
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [login, setLogin] = useState(false);

  const isWorker = user?.role === "worker";

  const load = useCallback(async () => {
    if (!isWorker) return;
    const [p, j, o, e, r] = await Promise.all([
      api.get<WorkerProfile>("/worker/profile"),
      api.get<Booking[]>("/worker/jobs"),
      api.get<Booking[]>("/worker/available-jobs"),
      api.get<Earnings>("/worker/earnings"),
      api.get<ServiceRequest[]>("/worker/service-requests"),
    ]);
    setProfile(p);
    setJobs(j);
    setOpen(o);
    setEarnings(e);
    setRequests(r);
  }, [isWorker]);

  useEffect(() => {
    api
      .get<Service[]>("/catalog/services", false)
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  useEffect(() => {
    load().catch(() => setJobs([]));
  }, [load]);

  // The pool is a race between workers, so it has to stay fresh without a
  // manual refresh — this is the worker's live queue. Pauses when the tab is
  // hidden; there is nobody looking at it.
  usePolling(() => load().catch(() => undefined), POLL_MS.worker, isWorker);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "That did not work.";
      // Losing a race is normal, not a failure — it deserves a toast the
      // worker can ignore, not a red box pinned to the page.
      if (e instanceof ApiError && e.code === "JOB_ALREADY_TAKEN") toast(message);
      else setError(message);
      // Either way the pool on screen is stale now.
      await load().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  const act = (b: Booking, path: string) =>
    run(`${b.id}:${path}`, () =>
      api.post(
        `/worker/jobs/${b.id}/${path}`,
        path === "complete"
          ? { cash_collected: true }
          : path === "reject"
            ? { reason: "Not available" }
            : undefined,
      ),
    );

  const claim = (b: Booking) =>
    run(`${b.id}:claim`, async () => {
      await api.post(`/worker/available-jobs/${b.id}/claim`);
      toast.success(`${b.service_name} is yours`, { description: b.reference });
    });

  const toggleAvailability = () =>
    run("availability", () =>
      api.patch<WorkerProfile>("/worker/profile", { is_available: !profile?.is_available }),
    );

  if (!ready) return <Spinner />;

  if (!isWorker) {
    return (
      <div className="mx-auto max-w-md space-y-4 text-center">
        <h1 className="text-3xl font-black">Worker portal</h1>
        <p className="muted text-sm">
          {user
            ? `You are signed in as a ${user.role}. Sign out and sign in with a worker number.`
            : "Sign in with a worker number to see open jobs and your schedule."}
        </p>
        <button className="btn-primary" onClick={() => setLogin(true)}>
          Sign in as worker
        </button>
        {login && <LoginDialog role="worker" onClose={() => setLogin(false)} />}
      </div>
    );
  }

  // Signing up is not finished until the worker has said what they do. Until
  // then there is no dashboard worth showing — no jobs can match, and the
  // verification the page talks about has nothing to review.
  if (profile && profile.services.length === 0) {
    return (
      <WorkerOnboarding
        services={services}
        name={user.full_name ?? "Welcome"}
        onDone={(updated) => {
          setProfile(updated);
          load().catch(() => undefined);
        }}
      />
    );
  }

  const active = (jobs ?? []).filter((j) => !["closed", "cancelled"].includes(j.status));
  const past = (jobs ?? []).filter((j) => ["closed", "cancelled"].includes(j.status));
  const myTrades = new Set(profile?.services.map((s) => s.service_id) ?? []);
  const verified = profile?.verification_status === "verified";
  const notice = profile && !verified ? VERIFICATION_COPY[profile.verification_status] : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-black">Worker portal</h1>
          <p className="muted mt-1 text-sm">{user.full_name ?? user.phone}</p>
        </div>
        {profile && (
          <button
            className={verified && profile.is_available ? "btn-primary" : "btn-ghost"}
            disabled={busy !== null || !verified}
            onClick={toggleAvailability}
            title={verified ? undefined : "Unlocked once your account is verified"}
          >
            <>
              <BadgeCheck size={15} />
              {profile.is_available ? "Available for work" : "Not taking jobs"}
            </>
          </button>
        )}
      </div>

      {notice && (
        <div className={`rounded-xl p-4 ${notice.tone}`}>
          <p className="font-bold">{notice.title}</p>
          <p className="mt-1 text-sm">{notice.body}</p>
          {profile?.verification_note && (
            <p className="mt-2 text-sm italic">Note from Sajilo: {profile.verification_note}</p>
          )}
        </div>
      )}

      {error && <ErrorNote message={error} />}

      {profile && (
        <TradePicker
          profile={profile}
          services={services}
          requests={requests}
          busy={busy}
          onRequest={async (serviceId, note) => {
            await api.post("/worker/service-requests", { service_id: serviceId, note: note || null });
            await load();
          }}
          onWithdraw={(id) =>
            run(`withdraw:${id}`, () => api.post(`/worker/service-requests/${id}/withdraw`))
          }
        />
      )}

      {earnings && (
        <div className="grid gap-3 sm:grid-cols-4">
          <Tile label="Jobs done" value={String(earnings.jobs_completed)} />
          <Tile label="Gross" value={npr(earnings.gross_amount)} />
          <Tile label="Commission" value={`− ${npr(earnings.commission_deducted)}`} />
          <Tile label="You earned" value={npr(earnings.net_earnings)} highlight icon={<Wallet size={14} />} />
        </div>
      )}

      {/* --- the claimable pool -------------------------------------------- */}
      {verified && (
        <section className="space-y-3">
          <div className="flex items-baseline gap-2">
            <h2 className="text-xl font-bold">Open jobs</h2>
            {open.length > 0 && (
              <span className="rounded-full bg-brand-600 px-2 py-0.5 text-xs font-bold text-white">
                {open.length}
              </span>
            )}
          </div>
          {open.length === 0 ? (
            <Empty
              title="No open jobs right now"
              hint={
                myTrades.size === 0
                  ? "Pick at least one trade above to start seeing jobs."
                  : "New bookings for your trades appear here within seconds."
              }
            />
          ) : (
            open.map((j) => (
              <div
                key={j.id}
                className="card animate-rise border-brand-300 p-5 dark:border-brand-700"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-bold">
                      {j.service_name} — {j.package_name}
                    </p>
                    <p className="muted font-mono text-xs">{j.reference}</p>
                  </div>
                  <p className="text-lg font-black text-brand-600 dark:text-brand-400">
                    {npr(j.worker_payout)}
                  </p>
                </div>

                <div className="muted mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                  <span className="inline-flex items-center gap-1.5"><Clock size={13} /> {when(j.scheduled_at)}</span>
                  <span className="inline-flex items-center gap-1.5"><Clock size={13} /> {duration(j.duration_minutes)}</span>
                  <span className="inline-flex items-center gap-1.5"><MapPin size={13} /> {j.address?.one_line}</span>
                </div>
                {j.notes && (
                  <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-500/10">
                    📝 {j.notes}
                  </p>
                )}

                <button
                  className="btn-primary mt-4 w-full sm:w-auto"
                  disabled={busy !== null}
                  onClick={() => claim(j)}
                >
                  {busy === `${j.id}:claim` ? "Taking it…" : "Accept this job"}
                </button>
              </div>
            ))
          )}
        </section>
      )}

      {/* --- my jobs ------------------------------------------------------- */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold">My jobs</h2>
        {jobs === null ? (
          <CardSkeleton rows={2} />
        ) : active.length === 0 ? (
          <Empty title="No active jobs" hint="Jobs you accept show up here." />
        ) : (
          active.map((j) => (
            <div key={j.id} className="card animate-rise p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-bold">
                    {j.service_name} — {j.package_name}
                  </p>
                  <p className="muted font-mono text-xs">{j.reference}</p>
                </div>
                <StatusBadge status={j.status} />
              </div>

              <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <p className="muted text-xs">Customer</p>
                  <p className="font-medium">{j.customer?.full_name ?? "—"}</p>
                  {j.customer?.phone && (
                    <a
                      href={`tel:${j.customer.phone}`}
                      className="text-brand-600 dark:text-brand-400"
                    >
                      {j.customer.phone}
                    </a>
                  )}
                </div>
                <div>
                  <p className="muted text-xs">Where and when</p>
                  <p className="font-medium">{j.address?.one_line}</p>
                  <p className="muted">
                    {when(j.scheduled_at)} · {duration(j.duration_minutes)}
                  </p>
                </div>
              </div>

              {j.notes && (
                <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-500/10">
                  📝 {j.notes}
                </p>
              )}

              <div
                className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="text-sm">
                  <span className="muted">Job value {npr(j.total_amount)} · </span>
                  <span className="font-bold">You get {npr(j.worker_payout)}</span>
                </div>
                <div className="flex gap-2">
                  {(NEXT_ACTION[j.status] ?? []).map((a) => (
                    <button
                      key={a.path}
                      className={a.path === "reject" ? "btn-ghost text-xs" : "btn-primary text-xs"}
                      disabled={busy !== null}
                      onClick={() => act(j, a.path)}
                    >
                      {busy === `${j.id}:${a.path}` ? "Working…" : a.label}
                    </button>
                  ))}
                  {j.status === "completed" && (
                    <span className="muted text-xs">Waiting for the customer to rate</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </section>

      {past.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-bold">Past jobs</h2>
          <div className="space-y-2">
            {past.map((j) => (
              <div key={j.id} className="card flex items-center justify-between p-4 text-sm">
                <div>
                  <p className="font-medium">{j.package_name}</p>
                  <p className="muted font-mono text-xs">{j.reference}</p>
                </div>
                <div className="flex items-center gap-3">
                  {j.review && (
                    <span className="text-accent-500">{"★".repeat(j.review.rating)}</span>
                  )}
                  <span className="font-semibold">{npr(j.worker_payout)}</span>
                  <StatusBadge status={j.status} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  highlight,
  icon,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className={`card p-4 ${highlight ? "border-brand-400 dark:border-brand-600" : ""}`}>
      <p className="muted flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide">
        {icon}
        {label}
      </p>
      <p
        className={`mt-1 text-xl font-black ${highlight ? "text-brand-600 dark:text-brand-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}
