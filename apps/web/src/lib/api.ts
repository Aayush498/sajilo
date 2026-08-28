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

async function parse(res: Response) {
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  return JSON.parse(text);
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = init;
  const h = new Headers(headers);
  h.set("Content-Type", "application/json");

  const token = tokens.access;
  if (auth && token) h.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, { ...rest, headers: h });
  const body = await parse(res);

  if (!res.ok) {
    const err = body?.error ?? {};
    // A dead session should not leave the UI in a half-authenticated state.
    if (res.status === 401 && auth) tokens.clear();
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
}

export interface Earnings {
  jobs_completed: number;
  gross_amount: string;
  commission_deducted: string;
  net_earnings: string;
}
