"use client";

import { useState } from "react";
import { ApiError, type Role } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorNote, Field } from "./ui";

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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-sm p-6 animate-rise"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold">
          {title ?? (role === "admin" ? "Admin sign in" : `Sign in as ${role}`)}
        </h2>
        <p className="muted mt-1 mb-5 text-sm">
          {role === "admin"
            ? "Use the seeded operations account."
            : "We'll text you a six-digit code."}
        </p>

        <div className="space-y-4">
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
                <input
                  className="input"
                  placeholder="9841234567"
                  value={phone}
                  disabled={sent}
                  onChange={(e) => setPhone(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !sent && send()}
                  inputMode="tel"
                />
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
                disabled={busy || (!sent && phone.length < 7)}
                onClick={sent ? verify : send}
              >
                {busy ? "Please wait…" : sent ? "Verify and continue" : "Send code"}
              </button>

              {sent && (
                <button className="muted w-full text-xs" onClick={() => setSent(false)}>
                  Use a different number
                </button>
              )}
            </>
          )}

          {role === "admin" && error && <ErrorNote message={error} />}
        </div>

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
      </div>
    </div>
  );
}
