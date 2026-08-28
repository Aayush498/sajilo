"use client";

import type { ReactNode } from "react";
import type { Booking, BookingStatus } from "@/lib/api";
import { PROGRESS_STEPS, STATUS_LABEL, STATUS_TONE, when } from "@/lib/format";

export function StatusBadge({ status }: { status: BookingStatus }) {
  const live = ["assigned", "accepted", "en_route", "in_progress"].includes(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_TONE[status]}`}
    >
      {live && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 muted text-sm">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      {label ?? "Loading…"}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="card p-10 text-center">
      <p className="font-semibold">{title}</p>
      {hint && <p className="muted mt-1 text-sm">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
      {message}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="label">{label}</span>
      {children}
    </div>
  );
}

/**
 * Horizontal progress tracker. Cancelled bookings get their own treatment
 * because they leave the happy path rather than advancing along it.
 */
export function ProgressTrack({ status }: { status: BookingStatus }) {
  if (status === "cancelled") {
    return (
      <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-800 dark:bg-rose-500/10 dark:text-rose-300">
        This booking was cancelled.
      </div>
    );
  }
  const current = PROGRESS_STEPS.indexOf(status);

  return (
    <div className="flex items-center">
      {PROGRESS_STEPS.map((step, i) => {
        const done = i <= current;
        const active = i === current;
        return (
          <div key={step} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={`h-3 w-3 shrink-0 rounded-full transition-colors ${
                  done ? "bg-brand-500" : "bg-slate-300 dark:bg-slate-700"
                } ${active ? "animate-pulse-ring" : ""}`}
              />
              <span
                className={`hidden text-[10px] leading-tight sm:block ${
                  done ? "text-brand-600 dark:text-brand-300 font-semibold" : "muted"
                }`}
              >
                {STATUS_LABEL[step]}
              </span>
            </div>
            {i < PROGRESS_STEPS.length - 1 && (
              <div
                className={`mx-1 h-0.5 flex-1 rounded transition-colors ${
                  i < current ? "bg-brand-500" : "bg-slate-200 dark:bg-slate-800"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function Timeline({ events }: { events: Booking["history"] }) {
  return (
    <ol className="space-y-3">
      {events.map((e, i) => (
        <li key={i} className="flex gap-3 text-sm">
          <div className="flex flex-col items-center">
            <span className="mt-1.5 h-2 w-2 rounded-full bg-brand-500" />
            {i < events.length - 1 && (
              <span className="w-px flex-1 bg-slate-200 dark:bg-slate-800" />
            )}
          </div>
          <div className="pb-2">
            <p className="font-medium capitalize">{e.action.replace(/_/g, " ")}</p>
            <p className="muted text-xs">
              {when(e.created_at)}
              {e.actor_role && ` · by ${e.actor_role}`}
              {e.note && ` · ${e.note}`}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Stars({ value, size = "text-base" }: { value: number; size?: string }) {
  return (
    <span className={`${size} text-accent-500`} aria-label={`${value} out of 5`}>
      {"★".repeat(value)}
      <span className="text-slate-300 dark:text-slate-700">{"★".repeat(5 - value)}</span>
    </span>
  );
}
