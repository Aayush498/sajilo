"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Booking } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { npr, when } from "@/lib/format";
import { Empty, Spinner, StatusBadge } from "@/components/ui";

export default function OrdersPage() {
  const { user, ready } = useAuth();
  const [bookings, setBookings] = useState<Booking[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api.get<Booking[]>("/bookings").then(setBookings).catch(() => setBookings([]));
  }, [user]);

  if (!ready) return <Spinner />;
  if (!user)
    return <Empty title="Sign in to see your orders" hint="Use the button in the header." />;
  if (bookings === null) return <Spinner label="Loading your orders…" />;
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
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
