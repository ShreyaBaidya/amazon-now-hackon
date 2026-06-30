"use client";
/**
 * useTimeRemaining
 * Returns a human-readable string for time remaining until a UTC ISO date.
 * Updates every minute automatically.
 */
import { useEffect, useState } from "react";

function format(dtUtc: string): string {
  const target = new Date(dtUtc);
  const now = new Date();
  const diffMs = target.getTime() - now.getTime();

  if (diffMs <= 0) return "Started";

  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 60) return `In ${diffMins}m`;
  if (diffHours < 24) return `In ${diffHours}h ${diffMins % 60}m`;
  if (diffDays === 1) return "Tomorrow";
  return `In ${diffDays} days`;
}

export function useTimeRemaining(dtUtc?: string | null): string | null {
  const [label, setLabel] = useState<string | null>(
    dtUtc ? format(dtUtc) : null
  );

  useEffect(() => {
    if (!dtUtc) {
      setLabel(null);
      return;
    }
    setLabel(format(dtUtc));
    const id = setInterval(() => setLabel(format(dtUtc)), 60_000);
    return () => clearInterval(id);
  }, [dtUtc]);

  return label;
}
