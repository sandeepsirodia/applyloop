import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

import { api, clearToken, getToken, setToken } from "@/lib/api";

interface AuthContext {
  authed: boolean;
  ready: boolean;
  login: (password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthContext | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // `applyloop ui` with no password configured prints a one-time link with ?t=<token> in the terminal;
    // picking it up here means that link keeps working exactly as before, with no login screen in the way.
    const urlToken = new URLSearchParams(window.location.search).get("t");
    if (urlToken) {
      setToken(urlToken);
      window.history.replaceState({}, "", window.location.pathname + window.location.hash);
    }
    setAuthed(!!getToken());
    setReady(true);
  }, []);

  const login = async (password: string) => {
    const token = await api.login(password);
    setToken(token);
    setAuthed(true);
  };
  const logout = () => {
    clearToken();
    setAuthed(false);
  };

  return <Ctx.Provider value={{ authed, ready, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
