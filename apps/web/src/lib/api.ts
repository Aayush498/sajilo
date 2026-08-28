/**
 * Typed client for the Sajilo API.
 *
 * Every error the backend returns shares one envelope, so `ApiError` carries
 * the machine-readable `code` and the UI branches on that rather than on
 * message text.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const ACCESS_KEY = "sajilo.access";
const REFRESH_KEY = "sajilo.refresh";
const USER_KEY = "sajilo.user";

export const tokens = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
  },
  save(session: AuthSession) {
    localStorage.setItem(ACCESS_KEY, session.access_token);
    localStorage.setItem(REFRESH_KEY, session.refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify(session.user));
  },
  saveUser(user: User) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  loadUser(): User | null {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  },
  clear() {
    [ACCESS_KEY, REFRESH_KEY, USER_KEY].forEach((k) => localStorage.removeItem(k));
  },
};

interface ApiBody {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
  [key: string]: unknown;
}

async function parse(res: Response): Promise<ApiBody | null> {
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  return JSON.parse(text);
}

/**
 * Called when a refresh fails and the session is genuinely over, so the app
 * can drop its user state instead of rendering a signed-in shell with no
 * token behind it. Set once by <AuthProvider>.
 */
let onSessionLost: (() => void) | null = null;
export function setSessionLostHandler(fn: () => void) {
  onSessionLost = fn;
}

/**
 * Access tokens live 15 minutes. Without this, every user was silently
 * signed out mid-task once theirs expired — the refresh token was being
 * stored and never used.
 *
 * The in-flight promise matters: a page that fires four requests at once
 * (as /worker does) would otherwise send four refreshes, and the API rotates
 * refresh tokens, so three of them would arrive with a token that had just
 * been consumed. Reuse detection would then revoke the whole session — the
 * exact opposite of staying signed in. Everyone awaits the same refresh.
 */
let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const token = tokens.refresh;
  if (!token) return false;

  refreshing ??= (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!res.ok) return false;
      tokens.save((await res.json()) as AuthSession);
      return true;
    } catch {
      return false;
    } finally {
      // Cleared in a microtask so everyone awaiting this round sees the
      // result before a later 401 can start a fresh attempt.
      queueMicrotask(() => {
        refreshing = null;
      });
    }
  })();

  return refreshing;
}

async function send(
  path: string,
  init: RequestInit & { auth?: boolean },
): Promise<{ res: Response; body: ApiBody | null }> {
  const { auth = true, headers, ...rest } = init;
  const h = new Headers(headers);
  h.set("Content-Type", "application/json");

  const token = tokens.access;
  if (auth && token) h.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...rest, headers: h });
  } catch {
    // fetch only rejects when the request never completed: the API is down,
    // DNS failed, or the device is offline. There is no status to report.
    throw new ApiError(
      "NETWORK",
      navigator.onLine === false
        ? "You appear to be offline. Check your connection and try again."
        : "Could not reach Sajilo. Please try again in a moment.",
      0,
    );
  }
  return { res, body: await parse(res) };
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const auth = init.auth ?? true;
  let { res, body } = await send(path, init);

  // One retry, and only for an authenticated call that we can actually fix by
  // getting a new access token.
  if (res.status === 401 && auth && tokens.refresh) {
    if (await refreshSession()) {
      ({ res, body } = await send(path, init));
    }
  }

  if (!res.ok) {
    const err = body?.error ?? {};
    // Still 401 after a refresh attempt: the session is genuinely gone.
    // Leaving the tokens behind would render a signed-in UI that 401s on
    // every action.
    if (res.status === 401 && auth) {
      tokens.clear();
      onSessionLost?.();
    }
    throw new ApiError(
      err.code ?? "UNKNOWN",
      err.message ?? `Request failed (${res.status})`,
      res.status,
      err.details ?? {},
    );
  }
  return body as T;
}

export const api = {
  get: <T>(p: string, auth = true) => request<T>(p, { method: "GET", auth }),
  post: <T>(p: string, body?: unknown, auth = true) =>
    request<T>(p, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      auth,
    }),
  put: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(p: string) => request<T>(p, { method: "DELETE" }),
};

// --- types ------------------------------------------------------------------

export type Role = "customer" | "worker" | "admin";

export type BookingStatus =
  | "pending"
  | "assigned"
  | "accepted"
  | "en_route"
  | "in_progress"
  | "completed"
  | "closed"
  | "cancelled";

export interface User {
  id: string;
  phone: string;
  full_name: string | null;
  email: string | null;
  role: Role;
  locale: string;
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: User;
  is_new_user: boolean;
}

export interface ServicePackage {
  id: string;
  name: string;
  name_ne: string | null;
  description: string | null;
  price: string;
  duration_minutes: number;
}

export interface Service {
  id: string;
  name: string;
  slug: string;
  name_ne: string | null;
  description: string | null;
  warranty_days: number;
  packages: ServicePackage[];
}

export interface City {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}

export interface Address {
  id: string;
  label: string;
  area: string;
  street: string | null;
  landmark: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  is_default: boolean;
  one_line: string;
}

export interface Person {
  id: string;
  full_name: string | null;
  phone: string | null;
  rating_avg: string | null;
  jobs_completed: number | null;
}

export interface StatusEvent {
  from_status: string | null;
  to_status: string;
  action: string;
  actor_role: string | null;
  note: string | null;
  created_at: string;
}

export interface Booking {
  id: string;
  reference: string;
  status: BookingStatus;
  service_name: string;
  package_name: string;
  quantity: number;
  unit_price: string;
  total_amount: string;
  duration_minutes: number;
  warranty_days: number;
  scheduled_at: string;
  notes: string | null;
  created_at: string;
  address: Address | null;
  customer: Person | null;
  worker: Person | null;
  payment: { method: string; status: string; amount: string; paid_at: string | null } | null;
  review: { rating: number; comment: string | null; created_at: string } | null;
  history: StatusEvent[];
  commission_amount: string | null;
  worker_payout: string | null;
}

export interface Quote {
  service_name: string;
  package_name: string;
  unit_price: string;
  quantity: number;
  total_amount: string;
  duration_minutes: number;
  warranty_days: number;
  commission_amount: string;
  worker_payout: string;
}

export interface WorkerSummary {
  user_id: string;
  full_name: string | null;
  phone: string;
  verification_status: string;
  is_available: boolean;
  rating_avg: string;
  rating_count: number;
  jobs_completed: number;
  service_names: string[];
}

export interface AdminStats {
  bookings_by_status: Record<string, number>;
  total_bookings: number;
  gross_booking_value: string;
  commission_revenue: string;
  customers: number;
  workers_pending_verification: number;
  pending_service_requests: number;
}

export interface WorkerProfile {
  id: string;
  user_id: string;
  bio: string | null;
  experience_years: number;
  verification_status: "pending" | "under_review" | "verified" | "rejected";
  verification_note: string | null;
  police_verified: boolean;
  is_available: boolean;
  rating_avg: string;
  rating_count: number;
  jobs_completed: number;
  services: { service_id: string; skill_verified: boolean }[];
  /** True once verification freezes the trade list. Decided server-side. */
  services_locked: boolean;
}

export interface ServiceRequest {
  id: string;
  service_id: string;
  service_name: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  note: string | null;
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
  worker_user_id: string | null;
  worker_name: string | null;
  worker_phone: string | null;
}

export interface Earnings {
  jobs_completed: number;
  gross_amount: string;
  commission_deducted: string;
  net_earnings: string;
}
