"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiError, api, type Booking } from "@/lib/api";
import { Modal } from "./Modal";

/**
 * Rating is no longer what closes a booking — paid work closes itself — so it
 * has to come and ask. Once the job settles the customer gets this prompt
 * instead of a form buried at the bottom of the page they may never scroll to.
 *
 * Dismissal is remembered per booking. Without that the prompt reappears on
 * every visit to a job the customer has already decided not to rate, which
 * turns a nudge into nagging.
 */

const DISMISS_PREFIX = "sajilo.review-dismissed.";

/** A finished job the customer has not rated, and can still rate. */
export function needsReview(booking: Booking): boolean {
  return (
    (booking.status === "closed" || booking.status === "completed") &&
    booking.review === null &&
    booking.worker !== null
  );
}

export function wasDismissed(bookingId: string): boolean {
  try {
    return localStorage.getItem(DISMISS_PREFIX + bookingId) !== null;
  } catch {
    // Private windows and blocked site data throw rather than returning null.
    // Losing the dismissal is better than losing the page.
    return false;
  }
}

export function dismiss(bookingId: string): void {
  try {
    localStorage.setItem(DISMISS_PREFIX + bookingId, "1");
  } catch {
    /* nothing to do; the prompt will simply ask again next time */
  }
}

export function ReviewDialog({
  booking,
  open,
  onClose,
  onReviewed,
}: {
  booking: Booking;
  open: boolean;
  onClose: () => void;
  onReviewed: (updated: Booking) => void;
}) {
  const [rating, setRating] = useState(5);
  const [hovered, setHovered] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  // A fresh prompt for a different job should not inherit the last one's stars.
  useEffect(() => {
    if (open) {
      setRating(5);
      setHovered(0);
      setComment("");
    }
  }, [open, booking.id]);

  async function submit() {
    setBusy(true);
    try {
      const updated = await api.post<Booking>(`/bookings/${booking.id}/review`, {
        rating,
        comment: comment.trim() || null,
      });
      onReviewed(updated);
      toast.success("Thanks for the rating", {
        description: `${booking.worker?.full_name ?? "Your professional"} will see it.`,
      });
      onClose();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save that rating.");
    } finally {
      setBusy(false);
    }
  }

  function later() {
    dismiss(booking.id);
    onClose();
  }

  const shown = hovered || rating;

  return (
    <Modal
      open={open}
      onClose={later}
      title="How did it go?"
      description={`${booking.service_name} · ${booking.package_name}`}
    >
      {booking.worker && (
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-full bg-brand-600 text-lg font-bold text-white">
            {booking.worker.full_name?.[0] ?? "?"}
          </div>
          <div>
            <p className="font-bold leading-tight">{booking.worker.full_name}</p>
            <p className="muted text-sm">Your professional</p>
          </div>
        </div>
      )}

      <div
        className="flex justify-center gap-1 text-4xl"
        onMouseLeave={() => setHovered(0)}
        role="radiogroup"
        aria-label="Rating out of five"
      >
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={n === rating}
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
            onMouseEnter={() => setHovered(n)}
            onFocus={() => setHovered(n)}
            onClick={() => setRating(n)}
            className={`transition-transform hover:scale-110 ${
              n <= shown ? "text-accent-500" : "text-slate-300 dark:text-slate-700"
            }`}
          >
            ★
          </button>
        ))}
      </div>

      <textarea
        className="input min-h-20"
        maxLength={1000}
        placeholder="Anything you'd like to add? (optional)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />

      <div className="flex gap-2">
        <button className="btn-ghost flex-1" onClick={later} disabled={busy}>
          Not now
        </button>
        <button className="btn-primary flex-1" onClick={submit} disabled={busy}>
          {busy ? "Sending…" : "Submit rating"}
        </button>
      </div>
    </Modal>
  );
}
