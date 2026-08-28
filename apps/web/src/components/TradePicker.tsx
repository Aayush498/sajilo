"use client";

import { useState } from "react";
import { Lock, Plus } from "lucide-react";
import { toast } from "sonner";
import { ApiError, api, type Service, type ServiceRequest, type WorkerProfile } from "@/lib/api";
import { SERVICE_EMOJI } from "@/lib/format";
import { Modal } from "./Modal";
import { Field } from "./ui";

const REQUEST_TONE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  rejected: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
  withdrawn: "bg-slate-200 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300",
};

/**
 * The worker's trade list, in one of two modes.
 *
 * Before verification it is editable. After verification it is frozen and a
 * change goes through support — the same rule the API enforces, read from
 * `services_locked` rather than re-derived here, so the two cannot drift.
 */
export function TradePicker({
  profile,
  services,
  requests,
  busy,
  onToggle,
  onRequest,
  onWithdraw,
}: {
  profile: WorkerProfile;
  services: Service[];
  requests: ServiceRequest[];
  busy: string | null;
  onToggle: (serviceId: string) => void;
  onRequest: (serviceId: string, note: string) => Promise<void>;
  onWithdraw: (requestId: string) => void;
}) {
  const [asking, setAsking] = useState<Service | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const mine = new Set(profile.services.map((s) => s.service_id));
  const locked = profile.services_locked;
  const pending = new Set(
    requests.filter((r) => r.status === "pending").map((r) => r.service_id),
  );
  const decided = requests.filter((r) => r.status !== "pending" && r.status !== "withdrawn");

  async function submit() {
    if (!asking) return;
    setSubmitting(true);
    try {
      await onRequest(asking.id, note.trim());
      toast.success(`Request sent for ${asking.name}`, {
        description: "Support will review it shortly.",
      });
      setAsking(null);
      setNote("");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not send that request.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-bold">
            What do you do?
            {locked && <Lock size={14} className="text-brand-600 dark:text-brand-400" />}
          </h2>
          <p className="muted mt-0.5 text-sm">
            {locked
              ? "Locked when Sajilo verified you. Ask support to add another trade."
              : "You only ever see jobs for the trades you pick here."}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {services.map((s) => {
          const on = mine.has(s.id);
          const waiting = pending.has(s.id);

          if (locked) {
            // Cleared trades read as facts; everything else is a request.
            return (
              <button
                key={s.id}
                disabled={on || waiting || busy !== null}
                onClick={() => setAsking(s)}
                title={on ? "You are cleared for this" : waiting ? "Waiting for support" : undefined}
                className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-all ${
                  on
                    ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200"
                    : waiting
                      ? "border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200"
                      : "hover:border-brand-400"
                }`}
                style={on || waiting ? undefined : { borderColor: "var(--border)" }}
              >
                <span>{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
                {s.name}
                {on ? <Lock size={12} /> : waiting ? <span className="text-xs">pending</span> : <Plus size={13} />}
              </button>
            );
          }

          return (
            <button
              key={s.id}
              disabled={busy !== null}
              onClick={() => onToggle(s.id)}
              className={`rounded-xl border px-3 py-2 text-sm font-medium transition-all disabled:opacity-50 ${
                on
                  ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200"
                  : "hover:border-brand-400"
              }`}
              style={on ? undefined : { borderColor: "var(--border)" }}
            >
              <span className="mr-1.5">{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
              {s.name}
              {on && <span className="ml-1.5">✓</span>}
            </button>
          );
        })}
      </div>

      {locked && requests.some((r) => r.status === "pending") && (
        <div className="mt-4 space-y-2 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="label">Waiting on support</p>
          {requests
            .filter((r) => r.status === "pending")
            .map((r) => (
              <div
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--surface-muted)" }}
              >
                <span className="font-medium">{r.service_name}</span>
                <button
                  className="btn-ghost text-xs"
                  disabled={busy !== null}
                  onClick={() => onWithdraw(r.id)}
                >
                  Withdraw
                </button>
              </div>
            ))}
        </div>
      )}

      {decided.length > 0 && (
        <div className="mt-4 space-y-2 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="label">Past requests</p>
          {decided.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{r.service_name}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${REQUEST_TONE[r.status]}`}
              >
                {r.status}
              </span>
              {r.decision_note && <span className="muted text-xs">— {r.decision_note}</span>}
            </div>
          ))}
        </div>
      )}

      <Modal
        open={asking !== null}
        onClose={() => setAsking(null)}
        title={`Request ${asking?.name ?? ""}`}
        description="Support reviews every trade before you can take those jobs."
      >
        <Field label="Why should we clear you? (optional)">
          <textarea
            className="input min-h-24"
            maxLength={1000}
            placeholder="Years of experience, certificates, past work…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <button className="btn-primary w-full" disabled={submitting} onClick={submit}>
          {submitting ? "Sending…" : "Send request"}
        </button>
      </Modal>
    </section>
  );
}
