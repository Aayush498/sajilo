"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { api, type Booking } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { POLL_MS, npr, when } from "@/lib/format";
import { ReviewDialog, needsReview, wasDismissed } from "@/components/ReviewDialog";
import { CardSkeleton, Empty, Spinner, StatusBadge } from "@/components/ui";

export default function OrdersPage() {
  const { user, ready } = useAuth();
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [rating, setRating] = useState<Booking | null>(null);

  const load = useCallback(async () => {
    setBookings(await api.get<Booking[]>("/bookings"));
  }, []);

  useEffect(() => {
    if (user) load().catch(() => setBookings([]));
  }, [user, load]);

  // A worker can finish a job while this list is open. Without polling the
  // customer sat looking at a stale "Work in progress" until they reloaded.
  usePolling(() => load().catch(() => undefined), POLL_MS.orders, !!user);

  // Prompt for the oldest finished job still waiting on a rating, skipping
  // any the customer has already dismissed.
  useEffect(() => {
    if (rating || !bookings) return;
    const unrated = bookings.filter((b) => needsReview(b) && !wasDismissed(b.id));
    if (unrated.length > 0) setRating(unrated[unrated.length - 1]);
  }, [bookings, rating]);

  if (!ready) return <Spinner />;
  if (!user)
    return <Empty title="Sign in to see your orders" hint="Use the button in the header." />;
  if (bookings === null)
    return (
      <div className="space-y-5">
        <h1 className="text-3xl font-black">My orders</h1>
        <CardSkeleton rows={3} />
      </div>
    );
  if (bookings.length === 0)
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-black">My orders</h1>
        <Empty title="No bookings yet" hint="Book a service and it will show up here." />
        <Link href="/book" className="btn-primary">
          Book a service
        </Link>
      </div>
    );

  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-black">My orders</h1>
      <div className="space-y-3">
        {bookings.map((b, i) => (
          <Link
            key={b.id}
            href={`/orders/${b.id}`}
            className="card animate-rise block p-5 transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-bold">{b.service_name}</p>
                <p className="muted text-sm">{b.package_name}</p>
                <p className="muted mt-1 font-mono text-xs">{b.reference}</p>
              </div>
              <div className="text-right">
                <StatusBadge status={b.status} />
                <p className="mt-2 text-lg font-bold">{npr(b.total_amount)}</p>
              </div>
            </div>
            <div
              className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t pt-3 text-xs muted"
              style={{ borderColor: "var(--border)" }}
            >
              <span>🗓️ {when(b.scheduled_at)}</span>
              {b.address && <span>📍 {b.address.one_line}</span>}
              {b.worker?.full_name && <span>👤 {b.worker.full_name}</span>}
              {/* Not a button: the whole card is already a link, and nesting
                  one inside the other breaks keyboard navigation. */}
              {needsReview(b) && (
                <span className="font-semibold text-brand-700 dark:text-brand-300">
                  ★ Rate this job
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>

      {rating && (
        <ReviewDialog
          booking={rating}
          open
          onClose={() => setRating(null)}
          onReviewed={(updated) =>
            setBookings((prev) =>
              (prev ?? []).map((b) => (b.id === updated.id ? updated : b)),
            )
          }
        />
      )}
    </div>
  );
}
