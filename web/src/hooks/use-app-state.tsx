import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

import { type AppState, ApiError, api, getToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Ctx {
  state: AppState | null;
  error: string | null;
  refresh: () => Promise<void>;
}

const StateCtx = createContext<Ctx | null>(null);

/** One poll (every 5s) and one live-event stream for the whole authed app, shared by the nav badges and
 * whichever page is mounted — not reopened per page. */
export function AppStateProvider({ children }: { children: ReactNode }) {
  const { authed, logout } = useAuth();
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.state();
      setState(s);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) logout();
      else setError(e instanceof Error ? e.message : "failed to load");
    }
  }, [logout]);

  useEffect(() => {
    if (!authed) return;
    refresh();
    const interval = setInterval(refresh, 5000);
    const token = getToken();
    const es = new EventSource("/api/events?t=" + encodeURIComponent(token || ""));
    es.onmessage = () => refresh();
    esRef.current = es;
    return () => {
      clearInterval(interval);
      es.close();
    };
  }, [authed, refresh]);

  return <StateCtx.Provider value={{ state, error, refresh }}>{children}</StateCtx.Provider>;
}

export function useAppState() {
  const ctx = useContext(StateCtx);
  if (!ctx) throw new Error("useAppState must be used inside AppStateProvider");
  return ctx;
}
