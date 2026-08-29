import type { BookingStatus } from "./api";

/** NPR 2,200 — no decimals, because nobody quotes paisa for a house clean. */
export function npr(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  const n = typeof amount === "string" ? Number(amount) : amount;
  if (Number.isNaN(n)) return "—";
  return `NPR ${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function duration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

export const STATUS_LABEL: Record<BookingStatus, string> = {
  pending: "Finding a professional",
  assigned: "Professional assigned",
  accepted: "Confirmed",
  en_route: "On the way",
  in_progress: "Work in progress",
  completed: "Completed",
  closed: "Closed",
  cancelled: "Cancelled",
};

export const STATUS_TONE: Record<BookingStatus, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  assigned: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  accepted: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  en_route: "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300",
  in_progress: "bg-brand-100 text-brand-800 dark:bg-brand-500/15 dark:text-brand-300",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  closed: "bg-slate-200 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300",
  cancelled: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
};

/**
 * Statuses a booking can still move out of without the viewer doing anything.
 *
 * Screens poll while a booking is in one of these and stop once it settles.
 * `completed` belongs here: an unpaid job sits there until the worker confirms
 * the cash, and the customer watching should see it close when they do.
 */
export const LIVE_STATUSES: BookingStatus[] = [
  "pending",
  "assigned",
  "accepted",
  "en_route",
  "in_progress",
  "completed",
];

export function isLive(status: BookingStatus): boolean {
  return LIVE_STATUSES.includes(status);
}

/**
 * How often each live screen refetches. Kept together so the whole app's
 * polling load is visible in one place rather than guessed at per file.
 */
export const POLL_MS = {
  /** One booking the customer is actively watching. */
  order: 3000,
  /** The customer's list of bookings. */
  orders: 6000,
  /** Worker portal: open pool plus their own jobs. */
  worker: 4000,
  /** Admin dispatch board. */
  admin: 6000,
} as const;

/** The happy path, in order. Used to draw the progress tracker. */
export const PROGRESS_STEPS: BookingStatus[] = [
  "pending",
  "assigned",
  "accepted",
  "en_route",
  "in_progress",
  "completed",
  "closed",
];

export const SERVICE_EMOJI: Record<string, string> = {
  "house-cleaning": "🧹",
  electrician: "💡",
  plumber: "🔧",
  carpenter: "🪚",
  "ac-repair": "❄️",
};
