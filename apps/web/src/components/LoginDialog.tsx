"use client";

import { useEffect, useState } from "react";
import { KeyRound, Loader2, Smartphone } from "lucide-react";
import { ApiError, type Role } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Modal } from "./Modal";
import { ErrorNote, Field } from "./ui";

/** The API's resend lock, mirrored so the button can say when it lifts. */
const RESEND_SECONDS = 60;

/**
 * Nepali mobiles are ten digits starting 97 or 98 (plus a few 96/972 ranges
 * libphonenumber accepts). This is a courtesy check to catch a typo before a
 * round trip — the API still validates properly with libphonenumber, and is
 * the authority.
 */
function looksLikeNepaliMobile(raw: string): boolean {
  const digits = raw.replace(/\D/g, "").replace(/^977/, "");
  return /^9[6-8]\d{8}$/.test(digits);
}

/**
 * Phone + OTP for customers and workers, email + password for admins.
 *
 * In dev the backend returns the OTP as `debug_code`, so we prefill it. That
 * is the difference between testing a booking in ten seconds and hunting
 * through docker logs for a six-digit number.
 */
export function LoginDialog({
  role,
  onClose,
  title,
}: {
  role: Role;
  onClose: () => void;
  title?: string;
}) {
  const { requestOtp, verifyOtp, adminLogin } = useAuth();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("admin@sajilo.com.np");
  const [password, setPassword] = useState("ChangeMeNow123!");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  // The API refuses a resend for a minute. Without a visible countdown people
  // tap "resend" and get an error for doing the obvious thing.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const typed = phone.trim().length > 0;
  const phoneLooksWrong = typed && !looksLikeNepaliMobile(phone);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const send = () =>
    run(async () => {
      const res = await requestOtp(phone, role as Role);
      setSent(true);
      setCooldown(RESEND_SECONDS);
      if (res.debug_code) setCode(res.debug_code);
    });

  const verify = () =>
    run(async () => {
      await verifyOtp(phone, code, role as Role);
      // A first-timer has no name yet; <ProfileGate> asks for it once this
      // closes. It has to live outside this dialog — signing in can unmount
      // the page that owns the dialog.
      onClose();
    });

  const signInAdmin = () =>
    run(async () => {
      await adminLogin(email, password);
      onClose();
    });

  return (
    <Modal
      open
      onClose={onClose}
      title={title ?? (role === "admin" ? "Admin sign in" : `Sign in as ${role}`)}
      description={
        role === "admin"
          ? "Use the seeded operations account."
          : "We'll text you a six-digit code."
      }
    >
      <>
          {role === "admin" ? (
            <>
              <Field label="Email">
                <input
                  className="input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                />
              </Field>
              <Field label="Password">
                <input
                  className="input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </Field>
              <button className="btn-primary w-full" disabled={busy} onClick={signInAdmin}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </>
          ) : (
            <>
              <Field label="Mobile number">
                <div className="flex items-center gap-2">
                  <span className="muted shrink-0 text-sm font-semibold">+977</span>
                  <input
                    className="input"
                    placeholder="9841234567"
                    value={phone}
                    disabled={sent}
                    onChange={(e) => setPhone(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !sent && !phoneLooksWrong && send()}
                    inputMode="tel"
                    autoComplete="tel"
                    aria-invalid={phoneLooksWrong}
                  />
                </div>
                {/* Caught while typing, rather than after a round trip that
                    comes back with a rejection. */}
                {phoneLooksWrong && !sent && (
                  <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                    That does not look like a Nepali mobile — ten digits starting 98 or 97.
                  </p>
                )}
              </Field>

              {sent && (
                <Field label="Verification code">
                  <input
                    className="input tracking-[0.4em] text-center text-lg font-semibold"
                    value={code}
                    maxLength={6}
                    onChange={(e) => setCode(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && verify()}
                    inputMode="numeric"
                    autoFocus
                  />
                  <p className="muted mt-2 text-xs">
                    Dev mode: no SMS is sent, so the code is filled in for you.
                  </p>
                </Field>
              )}

              {error && <ErrorNote message={error} />}

              <button
                className="btn-primary w-full"
                disabled={busy || (!sent && phoneLooksWrong) || (!sent && !typed)}
                onClick={sent ? verify : send}
              >
                {busy ? "Please wait…" : sent ? "Verify and continue" : "Send code"}
              </button>

              {sent && (
                <div className="flex items-center justify-between text-xs">
                  <button
                    className="muted disabled:opacity-60"
                    disabled={busy || cooldown > 0}
                    onClick={send}
                  >
                    {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
                  </button>
                  <button
                    className="muted"
                    onClick={() => {
                      setSent(false);
                      setCode("");
                      setError(null);
                    }}
                  >
                    Use a different number
                  </button>
                </div>
              )}
            </>
          )}

        {role === "admin" && error && <ErrorNote message={error} />}

        {role !== "admin" && (
          <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
            <p className="muted mb-2 text-xs font-semibold uppercase tracking-wide">
              Demo accounts
            </p>
            <div className="space-y-1 text-xs">
              {(role === "customer"
                ? [["Anjali Maharjan", "9841000100"]]
                : [
                    ["Ram Bahadur Thapa", "9841000001"],
                    ["Sita Gurung", "9841000002"],
                    ["Bikash Shrestha", "9841000003"],
                  ]
              ).map(([demoName, num]) => (
                <button
                  key={num}
                  className="flex w-full justify-between rounded-lg px-2 py-1 hover:bg-brand-50 dark:hover:bg-brand-900/40"
                  onClick={() => {
                    setPhone(num);
                    setSent(false);
                  }}
                >
                  <span>{demoName}</span>
                  <span className="muted font-mono">{num}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </>
    </Modal>
  );
}
