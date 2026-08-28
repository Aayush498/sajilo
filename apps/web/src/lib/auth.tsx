"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, tokens, type AuthSession, type Role, type User } from "./api";

export interface ProfilePatch {
  full_name?: string;
  email?: string | null;
  locale?: string;
}

interface AuthState {
  user: User | null;
  ready: boolean;
  requestOtp: (phone: string, role: Role) => Promise<{ debug_code: string | null }>;
  verifyOtp: (phone: string, code: string, role: Role) => Promise<User>;
  adminLogin: (email: string, password: string) => Promise<User>;
  updateProfile: (patch: ProfilePatch) => Promise<User>;
  logout: () => Promise<void>;
  logoutEverywhere: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // `ready` guards against rendering a signed-out view for one frame before
  // localStorage has been read — that flicker looks broken.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUser(tokens.loadUser());
    setReady(true);
  }, []);

  const adopt = useCallback((session: AuthSession) => {
    tokens.save(session);
    setUser(session.user);
    return session.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      requestOtp: (phone, role) =>
        api.post<{ debug_code: string | null }>(
          "/auth/request-otp",
          { phone, role },
          false,
        ),
      verifyOtp: async (phone, code, role) =>
        adopt(await api.post<AuthSession>("/auth/verify-otp", { phone, code, role }, false)),
      adminLogin: async (email, password) =>
        adopt(await api.post<AuthSession>("/auth/admin/login", { email, password }, false)),
      updateProfile: async (patch) => {
        const updated = await api.patch<User>("/users/me", patch);
        // The cached user is what the header and every role guard read, so it
        // has to move with the server or the UI shows a stale name.
        tokens.saveUser(updated);
        setUser(updated);
        return updated;
      },
      logout: async () => {
        const refresh = tokens.refresh;
        // Best effort: if the network call fails we still drop local state,
        // otherwise the user is stuck "logged in" on a broken session.
        if (refresh) {
          try {
            await api.post("/auth/logout", { refresh_token: refresh }, false);
          } catch {
            /* ignore */
          }
        }
        tokens.clear();
        setUser(null);
      },
      logoutEverywhere: async () => {
        // Revokes every session server-side, so a lost phone cannot stay
        // signed in. Needs the access token, so it runs before clearing.
        try {
          await api.post("/auth/logout-all");
        } catch {
          /* fall through — local state must still be dropped */
        }
        tokens.clear();
        setUser(null);
      },
    }),
    [user, ready, adopt],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
