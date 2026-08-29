"use client";

import { useState } from "react";
import { AlertTriangle, ArrowRight, Lock } from "lucide-react";
import { toast } from "sonner";
import { ApiError, api, type Service, type WorkerProfile } from "@/lib/api";
import { SERVICE_EMOJI } from "@/lib/format";
import { Spinner } from "./ui";

/**
 * The last step of signing up as a professional, and a gate: a worker with no
 * declared trades gets this instead of the dashboard.
 *
 * It is deliberately a whole screen rather than a card inside the portal. The
 * choice is permanent — the list locks the moment it is submitted, and
 * widening it goes through support — so it should not look like one more
 * setting among many that can be revised later.
 */
export function WorkerOnboarding({
  services,
  name,
  onDone,
}: {
  services: Service[];
  name: string;
  onDone: (profile: WorkerProfile) => void;
}) {
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  function toggle(id: string) {
    setChosen((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  async function submit() {
    if (chosen.size === 0) return;
    setBusy(true);
    try {
      const profile = await api.put<WorkerProfile>("/worker/services", {
        service_ids: [...chosen],
      });
      toast.success("Sent to Sajilo for verification", {
        description: "You will be able to take jobs as soon as you are approved.",
      });
      onDone(profile);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (services.length === 0) return <Spinner label="Loading trades…" />;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <p className="label">Step 2 of 2 · almost there</p>
        <h1 className="mt-1 text-3xl font-black">What do you do?</h1>
        <p className="muted mt-2">
          {name}, pick every trade you work in. You will only ever be shown jobs for these —
          a plumber is never sent an AC job.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {services.map((s) => {
          const on = chosen.has(s.id);
          return (
            <button
              key={s.id}
              onClick={() => toggle(s.id)}
              disabled={busy}
              aria-pressed={on}
              className={`card flex items-center gap-3 p-4 text-left transition-all disabled:opacity-60 ${
                on
                  ? "border-brand-500 bg-brand-50 dark:bg-brand-900/30"
                  : "hover:-translate-y-0.5 hover:border-brand-400"
              }`}
            >
              <span className="text-2xl">{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
              <span className="flex-1">
                <span className="block font-bold">{s.name}</span>
                <span className="muted block text-xs">{s.description}</span>
              </span>
              <span
                className={`grid h-5 w-5 shrink-0 place-items-center rounded-md border text-xs font-bold ${
                  on ? "border-brand-500 bg-brand-600 text-white" : ""
                }`}
                style={on ? undefined : { borderColor: "var(--border)" }}
              >
                {on ? "✓" : ""}
              </span>
            </button>
          );
        })}
      </div>

      {/* Said before they commit, not discovered afterwards. */}
      <div className="flex gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <p>
          <b>This locks once you continue.</b> Sajilo verifies each professional against the
          trades they declared, so you cannot change the list yourself afterwards — adding
          another one goes to support for review.
        </p>
      </div>

      <button
        className="btn-primary w-full justify-center py-3 text-base"
        disabled={busy || chosen.size === 0}
        onClick={submit}
      >
        {busy ? (
          "Submitting…"
        ) : chosen.size === 0 ? (
          "Pick at least one trade"
        ) : (
          <>
            <Lock size={15} />
            Continue with {chosen.size} {chosen.size === 1 ? "trade" : "trades"}
            <ArrowRight size={15} />
          </>
        )}
      </button>
    </div>
  );
}
