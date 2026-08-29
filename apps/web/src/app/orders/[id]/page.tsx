"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, api, type Booking } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { POLL_MS, duration, isLive, npr, when } from "@/lib/format";
import { ReviewDialog, needsReview, wasDismissed } from "@/components/ReviewDialog";
import {
  Empty,
  ErrorNote,
  ProgressTrack,
  Spinner,
  Stars,
  StatusBadge,
  Timeline,
} from "@/components/ui";

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, ready } = useAuth();

  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rateOpen, setRateOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setBooking(await api.get<Booking>(`/bookings/${id}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this booking.");
    }
  }, [id]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  // Poll while the job can still move on its own. Server-sent events would be
  // tidier, but polling needs no extra infrastructure and a three second lag
  // is invisible here. Stops while the tab is hidden and refetches the moment
  // it comes back.
  usePolling(load, POLL_MS.order, !!booking && isLive(booking.status));

  // The job settles while the customer is watching it, so ask for the rating
  // right then. Anything they have already waved away stays waved away.
  useEffect(() => {
    if (booking && needsReview(booking) && !wasDismissed(booking.id)) setRateOpen(true);
  }, [booking]);

  async function act(fn: () => Promise<Booking>) {
    setBusy(true);
    setError(null);
    try {
      setBooking(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <Spinner />;
  if (!user) return <Empty title="Sign in to view this booking" />;
  if (error && !booking) return <ErrorNote message={error} />;
  if (!booking) return <Spinner label="Loading booking…" />;

  const canCancel = ["pending", "assigned", "accepted", "en_route"].includes(booking.status);
  const canRate = needsReview(booking);

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/orders" className="muted text-sm hover:underline">
        ← All orders
      </Link>

      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="muted font-mono text-xs">{booking.reference}</p>
            <h1 className="mt-1 text-2xl font-black">{booking.service_name}</h1>
            <p className="muted">{booking.package_name}</p>
          </div>
          <StatusBadge status={booking.status} />
        </div>

        <div className="mt-6">
          <ProgressTrack status={booking.status} />
        </div>
      </div>

      {booking.worker && (
        <div className="card p-5">
          <p className="label">Your professional</p>
          <div className="flex items-center gap-4">
            <div className="grid h-14 w-14 place-items-center rounded-full bg-brand-600 text-xl font-bold text-white">
              {booking.worker.full_name?.[0] ?? "?"}
            </div>
            <div className="flex-1">
              <p className="font-bold">{booking.worker.full_name}</p>
              <p className="muted text-sm">
                {Number(booking.worker.rating_avg ?? 0) > 0 && (
                  <>
                    <Stars value={Math.round(Number(booking.worker.rating_avg))} size="text-xs" />{" "}
                    {Number(booking.worker.rating_avg).toFixed(1)} ·{" "}
                  </>
                )}
                {booking.worker.jobs_completed ?? 0} jobs completed
              </p>
            </div>
            {booking.worker.phone && (
              <a href={`tel:${booking.worker.phone}`} className="btn-primary text-xs">
                📞 Call
              </a>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="card p-5">
          <p className="label">Details</p>
          <dl className="space-y-2 text-sm">
            <Row k="Scheduled" v={when(booking.scheduled_at)} />
            <Row k="Duration" v={`about ${duration(booking.duration_minutes)}`} />
            <Row k="Address" v={booking.address?.one_line ?? "—"} />
            <Row k="Warranty" v={`${booking.warranty_days} days`} />
            {booking.notes && <Row k="Notes" v={booking.notes} />}
          </dl>
        </div>

        <div className="card p-5">
          <p className="label">Payment</p>
          <dl className="space-y-2 text-sm">
            <Row k={`${booking.package_name} × ${booking.quantity}`} v={npr(booking.unit_price)} />
            <div
              className="flex justify-between border-t pt-2 text-base font-bold"
              style={{ borderColor: "var(--border)" }}
            >
              <dt>Total</dt>
              <dd>{npr(booking.total_amount)}</dd>
            </div>
            {booking.payment && (
              <Row
                k="Status"
                v={`${booking.payment.method} · ${booking.payment.status}`}
              />
            )}
          </dl>
        </div>
      </div>

      {booking.review && (
        <div className="card p-5">
          <p className="label">Your rating</p>
          <Stars value={booking.review.rating} />
          {booking.review.comment && <p className="mt-2 text-sm">{booking.review.comment}</p>}
        </div>
      )}

      {canRate && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-brand-300 p-5 dark:border-brand-700">
          <div>
            <p className="font-bold">How did it go?</p>
            <p className="muted text-sm">
              {booking.worker?.full_name ?? "Your professional"} would like to know.
            </p>
          </div>
          <button className="btn-primary" onClick={() => setRateOpen(true)}>
            Rate this job
          </button>
        </div>
      )}

      <ReviewDialog
        booking={booking}
        open={rateOpen}
        onClose={() => setRateOpen(false)}
        onReviewed={setBooking}
      />

      {error && <ErrorNote message={error} />}

      {canCancel && (
        <button
          className="btn-ghost w-full text-rose-600 dark:text-rose-400"
          disabled={busy}
          onClick={() =>
            act(() =>
              api.post<Booking>(`/bookings/${booking.id}/cancel`, {
                reason: "Cancelled by customer",
              }),
            )
          }
        >
          Cancel this booking
        </button>
      )}

      <div className="card p-5">
        <p className="label">History</p>
        <Timeline events={booking.history} />
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="muted shrink-0">{k}</dt>
      <dd className="text-right font-medium capitalize">{v}</dd>
    </div>
  );
}
