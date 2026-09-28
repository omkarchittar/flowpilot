"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { Session } from "@/lib/types";

interface Auth {
  session: Session | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}
const Context = createContext<Auth | null>(null);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Session>("/auth/me", { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setSession(data);
          setError(null);
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setSession(null);
          setError(
            cause instanceof ApiError && cause.status === 401
              ? null
              : errorMessage(cause),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    const expired = () => {
      setSession(null);
      setError(null);
    };
    window.addEventListener("session-expired", expired);
    return () => {
      controller.abort();
      window.removeEventListener("session-expired", expired);
    };
  }, [attempt]);
  const login = useCallback(async (email: string, password: string) => {
    const data = await api<Session>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(data);
    setError(null);
  }, []);
  const logout = useCallback(async () => {
    if (session)
      await api<void>("/auth/logout", { method: "POST" }, session.csrf_token);
    setSession(null);
  }, [session]);
  return (
    <Context.Provider
      value={{
        session,
        loading,
        error,
        login,
        logout,
        retry: () => {
          setLoading(true);
          setAttempt((x) => x + 1);
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const context = useContext(Context);
  if (!context) throw new Error("Auth provider is required");
  return context;
}
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { session, loading, error, retry } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !session && !error) router.replace("/login");
  }, [session, loading, error, router]);
  if (loading || (!session && !error))
    return (
      <div className="full-state" role="status">
        <span className="spinner" />
        Opening your workspace…
      </div>
    );
  if (error)
    return (
      <div className="full-state">
        <p role="alert">{error}</p>
        <button className="button" onClick={retry}>
          Try again
        </button>
      </div>
    );
  return <div key={session!.user.id}>{children}</div>;
}
