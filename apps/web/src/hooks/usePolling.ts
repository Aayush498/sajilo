"use client";

import { useEffect, useRef } from "react";

/**
 * Runs `fn` on an interval, but only while the tab is actually visible.
 *
 * Every live screen in Sajilo polls. Left on a background tab overnight that
 * is thousands of pointless requests per user, and browsers throttle
 * background timers unpredictably anyway, so the data was not fresh either.
 * Coming back to the tab refetches immediately rather than waiting out the
 * remainder of an interval.
 */
export function usePolling(fn: () => void, intervalMs: number, enabled = true) {
  // Kept in a ref so a caller passing an inline closure does not restart the
  // timer on every render.
  const latest = useRef(fn);
  latest.current = fn;

  useEffect(() => {
    if (!enabled) return;

    let timer: ReturnType<typeof setInterval> | null = null;

    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };

    const start = () => {
      stop();
      timer = setInterval(() => latest.current(), intervalMs);
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        latest.current();
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs, enabled]);
}
