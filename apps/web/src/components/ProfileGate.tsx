"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Modal } from "./Modal";
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
    // Not dismissable: an account with no name is useless to the person on
    // the other side of the job, so Escape and click-outside are disabled.
    // "Sign out instead" is the way out.
    <Modal
      open
      onClose={() => undefined}
      dismissable={false}
      title="One last thing"
      description={
        user.role === "worker"
          ? "Customers see this name when you take their job."
          : "So your professional knows who they are meeting."
      }
    >
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

      <button className="muted w-full text-xs" onClick={logout}>
        Sign out instead
      </button>
    </Modal>
  );
}
