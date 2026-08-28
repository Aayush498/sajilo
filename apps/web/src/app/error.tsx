"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * Catches any render or data error below the layout. Without it Next.js
 * shows its own stack-trace page, which is not something a customer in the
 * middle of a booking should ever see.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled UI error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400">
        <AlertTriangle size={26} />
      </div>
      <h1 className="mt-5 text-2xl font-black">Something went wrong</h1>
      <p className="muted mt-2 text-sm">
        This is on us, not you. Your bookings are safe — try again, and if it keeps
        happening, contact Sajilo support.
      </p>
      {error.digest && (
        <p className="muted mt-3 font-mono text-xs">Reference: {error.digest}</p>
      )}
      <button className="btn-primary mt-6 inline-flex" onClick={reset}>
        <RotateCw size={15} />
        Try again
      </button>
    </div>
  );
}
