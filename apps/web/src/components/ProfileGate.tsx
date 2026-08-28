"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorNote, Field } from "./ui";

/**
 * Blocks a signed-in user who has no name until they give one.
 *
 * This lives in the root layout rather than inside LoginDialog on purpose.
 * Signing in changes the very state that pages branch on, so a prompt owned
 * by the dialog gets unmounted mid-flow — /worker rendered its dialog inside
 * an `if (!isWorker)` early return, so a new worker signed in, the branch
 * flipped, the dialog vanished, and the account reached admin approval with
 * no name on it. A gate above the router cannot be torn down that way, and it
 * also catches accounts that are already nameless.
 */
export function ProfileGate() {
  const { user, ready, updateProfile, logout } = useAuth();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ready || !user || user.full_name) return null;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await updateProfile({ full_name: name.trim() });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save your name.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-gate-title"
    >
      <div className="card animate-rise w-full max-w-sm p-6">
        <h2 id="profile-gate-title" className="text-lg font-bold">
          One last thing
        </h2>
        <p className="muted mt-1 mb-5 text-sm">
          {user.role === "worker"
            ? "Customers see this name when you take their job."
            : "So your professional knows who they are meeting."}
        </p>

        <div className="space-y-4">
          <Field label="Your full name">
            <input
              className="input"
              placeholder="Anjali Maharjan"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && name.trim().length > 1 && save()}
              autoFocus
            />
          </Field>

          {error && <ErrorNote message={error} />}

          <button
            className="btn-primary w-full"
            disabled={busy || name.trim().length < 2}
            onClick={save}
          >
            {busy ? "Saving…" : "Continue"}
          </button>

          {/* Without this the only way out of the gate is clearing site data. */}
          <button className="muted w-full text-xs" onClick={logout}>
            Sign out instead
          </button>
        </div>
      </div>
    </div>
  );
}
