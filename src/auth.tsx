import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { friendlyAuthError } from "./authValidation";
import { useApp } from "./state";
import { supabase, supabaseConfigured } from "./supabase";

/** Every action resolves to this shape. `error` is a user-safe message; `notice` is an informational one. */
export interface AuthResult {
  error: string;
  notice: string;
}

interface AuthState {
  configured: boolean;
  /** True until the stored session (if any) has been read. */
  loading: boolean;
  user: User | null;
  /** True after the user opens a password-reset link, until a new password is saved. */
  recovery: boolean;
  signUp: (email: string, password: string) => Promise<AuthResult>;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signOut: () => Promise<AuthResult>;
  resetPassword: (email: string) => Promise<AuthResult>;
  updatePassword: (password: string) => Promise<AuthResult>;
}

const Context = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(Context);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

const ok = (notice = ""): AuthResult => ({ error: "", notice });
const fail = (message: string | undefined): AuthResult => ({ error: friendlyAuthError(message), notice: "" });
const unavailable = (): AuthResult => ({ error: "Accounts are not set up on this deployment.", notice: "" });

// Email links send people back here. The trailing slash keeps this matching a "…/**" entry in
// Supabase's Redirect URLs allow-list. There is deliberately no #/page part: with PKCE the
// ?code= parameter is exchanged and removed automatically.
const redirectUrl = () => `${window.location.origin}/`;

export function AuthProvider({ children }: { children: ReactNode }) {
  const { go } = useApp();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(supabaseConfigured);
  const [recovery, setRecovery] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    let live = true;

    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (live) setUser(data.session?.user ?? null);
      })
      .catch(() => undefined)
      .finally(() => {
        if (live) setLoading(false);
      });

    // Keep this callback synchronous: calling other Supabase methods inside it can deadlock the client.
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (!live) return;
      setUser(session?.user ?? null);
      setLoading(false);
      if (event === "PASSWORD_RECOVERY") {
        setRecovery(true);
        go("account");
      } else if (event === "SIGNED_OUT") {
        setRecovery(false);
      }
    });

    return () => {
      live = false;
      data.subscription.unsubscribe();
    };
  }, [go]);

  const signUp = useCallback<AuthState["signUp"]>(async (email, password) => {
    if (!supabase) return unavailable();
    const { data, error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: redirectUrl() } });
    if (error) return fail(error.message);
    // With "Confirm email" turned on there is no session yet. The message is the same whether or not
    // the address was already registered, so this form cannot be used to discover who has an account.
    return data.session ? ok("Account created. You're signed in.") : ok("Check your email to confirm your account, then sign in.");
  }, []);

  const signIn = useCallback<AuthState["signIn"]>(async (email, password) => {
    if (!supabase) return unavailable();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return error ? fail(error.message) : ok();
  }, []);

  const signOut = useCallback<AuthState["signOut"]>(async () => {
    if (!supabase) return unavailable();
    // "local" ends the session on this device only, not on the user's other devices.
    const { error } = await supabase.auth.signOut({ scope: "local" });
    return error ? fail(error.message) : ok();
  }, []);

  const resetPassword = useCallback<AuthState["resetPassword"]>(async (email) => {
    if (!supabase) return unavailable();
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: redirectUrl() });
    if (error) return fail(error.message);
    return ok("If an account exists for that email, a password-reset link is on its way.");
  }, []);

  const updatePassword = useCallback<AuthState["updatePassword"]>(async (password) => {
    if (!supabase) return unavailable();
    const { error } = await supabase.auth.updateUser({ password });
    if (error) return fail(error.message);
    setRecovery(false);
    return ok("Password updated.");
  }, []);

  const value = useMemo<AuthState>(
    () => ({ configured: supabaseConfigured, loading, user, recovery, signUp, signIn, signOut, resetPassword, updatePassword }),
    [loading, user, recovery, signUp, signIn, signOut, resetPassword, updatePassword],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
