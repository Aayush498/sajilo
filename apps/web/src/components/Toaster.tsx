"use client";

import { Toaster as Sonner } from "sonner";

/**
 * App-wide toasts, themed to match the design tokens rather than sonner's
 * defaults so they do not look bolted on.
 *
 * These replace the inline error boxes for *transient* results — "job
 * taken", "saved", "another professional got there first". Errors that a
 * form needs to keep showing next to a field still use <ErrorNote>, because
 * a toast that has faded cannot be re-read.
 */
export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      closeButton
      toastOptions={{
        style: {
          background: "var(--surface-raised)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        },
      }}
    />
  );
}
