import React, { createContext, useCallback, useContext, useEffect, useState, useRef } from "react";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { Platform } from "react-native";
import { apiGet, apiPost, setInMemoryToken } from "../api";
import { clearToken, getToken, saveToken } from "./token-store";

WebBrowser.maybeCompleteAuthSession();

export type AuthUser = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  phone_number?: string | null;
  sms_opt_in?: boolean;
};

type AuthContextType = {
  user: AuthUser | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  devSignIn: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | null>(null);

const processed = new Set<string>();

function extractSessionId(url: string | null): string | null {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const capturedUrlRef = useRef<string | null>(null);

  const exchangeSessionId = useCallback(async (sid: string) => {
    if (processed.has(sid)) return;
    processed.add(sid);
    try {
      const resp = await apiPost<{ session_token: string; user: AuthUser }>(
        "/auth/session",
        { session_id: sid },
      );
      await saveToken(resp.session_token);
      setInMemoryToken(resp.session_token);
      setUser(resp.user);
    } catch (e) {
      console.warn("session exchange failed", e);
    }
  }, []);

  useEffect(() => {
    let sub: any;
    (async () => {
      if (Platform.OS !== "web") {
        sub = Linking.addEventListener("url", ({ url }) => {
          capturedUrlRef.current = url;
          const sid = extractSessionId(url);
          if (sid) exchangeSessionId(sid);
        });
        const initial = await Linking.getInitialURL();
        const sid = extractSessionId(initial);
        if (sid) {
          await exchangeSessionId(sid);
        }
      } else {
        const url = typeof window !== "undefined" ? window.location.href : "";
        const sid = extractSessionId(url);
        if (sid) {
          await exchangeSessionId(sid);
          try {
            const cleanUrl = window.location.pathname + window.location.search.replace(/[?&]session_id=[^&]+/, "").replace(/^\?$/, "");
            window.history.replaceState(window.history.state, "", cleanUrl || "/");
          } catch {}
        }
      }

      // Load existing token
      const t = await getToken();
      if (t) {
        setInMemoryToken(t);
        try {
          const me = await apiGet<AuthUser>("/auth/me");
          setUser(me);
        } catch {
          await clearToken();
          setInMemoryToken(null);
          setUser(null);
        }
      }
      setLoading(false);
    })();
    return () => { sub?.remove?.(); };
  }, [exchangeSessionId]);

  const signIn = useCallback(async () => {
    const redirectUrl =
      Platform.OS === "web"
        ? (typeof window !== "undefined" ? window.location.origin + "/" : "/")
        : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === "web") {
      window.location.href = authUrl;
      return;
    }
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    let url = (result as any)?.url as string | undefined;
    if (!url) url = capturedUrlRef.current || undefined;
    if (!url) url = (await Linking.getInitialURL()) || undefined;
    const sid = extractSessionId(url || null);
    if (sid) await exchangeSessionId(sid);
  }, [exchangeSessionId]);

  const signOut = useCallback(async () => {
    try { await apiPost("/auth/logout"); } catch {}
    await clearToken();
    setInMemoryToken(null);
    setUser(null);
  }, []);

  // Demo/dev sign-in: creates a fake session by calling backend directly with a special dev token.
  const devSignIn = useCallback(async () => {
    try {
      const resp = await apiPost<{ session_token: string; user: AuthUser }>(
        "/auth/dev-login",
        {},
      );
      await saveToken(resp.session_token);
      setInMemoryToken(resp.session_token);
      setUser(resp.user);
    } catch (e) {
      console.warn("dev sign-in failed", e);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, devSignIn }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
