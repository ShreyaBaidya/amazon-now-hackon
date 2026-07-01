"use client";
/**
 * useGoogleCalendar
 *
 * Manages Google Calendar connection state for the current browser session.
 * - Checks connection status on mount.
 * - Detects the ?calendar_connected=1 / ?calendar_error=... query params
 *   written by the backend OAuth callback redirect.
 * - Exposes connect / disconnect / refresh actions.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export type CalendarConnectionState =
  | "idle"        // not yet checked
  | "checking"    // fetching status
  | "connected"   // Google Calendar is live
  | "disconnected" // not connected, using mock
  | "no_credentials" // server missing CLIENT_ID/SECRET
  | "error";      // connection attempt failed

export interface UseGoogleCalendarReturn {
  state: CalendarConnectionState;
  errorMsg: string | null;
  connect: () => void;         // redirects to Google OAuth
  disconnect: () => Promise<void>;
  refresh: () => Promise<void>;
  isLoading: boolean;
}

export function useGoogleCalendar(): UseGoogleCalendarReturn {
  const [state, setState] = useState<CalendarConnectionState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const checkStatus = useCallback(async () => {
    setIsLoading(true);
    try {
      const status = await api.calendarStatus();
      if (status.connected) {
        setState("connected");
      } else if (!status.has_credentials) {
        setState("no_credentials");
      } else {
        setState("disconnected");
      }
    } catch {
      setState("disconnected");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // On mount: check for OAuth callback params, then check status
  useEffect(() => {
    if (typeof window === "undefined") return;

    const url = new URL(window.location.href);
    const connected = url.searchParams.get("calendar_connected");
    const error = url.searchParams.get("calendar_error");

    if (connected === "1") {
      // Clean the URL so reload doesn't re-trigger
      url.searchParams.delete("calendar_connected");
      window.history.replaceState({}, "", url.toString());
      setState("connected");
      setIsLoading(false);
      return;
    }

    if (error) {
      url.searchParams.delete("calendar_error");
      window.history.replaceState({}, "", url.toString());
      setErrorMsg(`Google Calendar connection failed: ${error}`);
      setState("error");
      setIsLoading(false);
      return;
    }

    checkStatus();
  }, [checkStatus]);

  const connect = useCallback(() => {
    // Redirect the browser to the backend's OAuth auth URL
    window.location.href = api.calendarAuthUrl();
  }, []);

  const disconnect = useCallback(async () => {
    setIsLoading(true);
    try {
      await api.calendarDisconnect();
      setState("disconnected");
      setErrorMsg(null);
    } catch {
      setErrorMsg("Failed to disconnect. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (state !== "connected") return;
    setIsLoading(true);
    try {
      await api.calendarRefresh();
      // NextBuy will re-fetch automatically; just clear any error
      setErrorMsg(null);
    } catch {
      setErrorMsg("Could not refresh calendar data.");
    } finally {
      setIsLoading(false);
    }
  }, [state]);

  return { state, errorMsg, connect, disconnect, refresh, isLoading };
}
