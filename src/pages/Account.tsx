import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { MIN_PASSWORD, validateEmail, validatePassword } from "../authValidation";
import { ErrorNote, Loading } from "../components/Status";

type Mode = "signin" | "signup" | "forgot";

const TITLES: Record<Mode, string> = {
  signin: "Sign in",
  signup: "Create your account",
  forgot: "Reset your password",
};

function AuthForm() {
  const { signIn, signUp, resetPassword } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
    setNotice("");
    setPassword("");
    setConfirm("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    setNotice("");

    const emailProblem = validateEmail(email);
    if (emailProblem) {
      setError(emailProblem);
      return;
    }
    if (mode === "signin" && !password) {
      setError("Enter your password.");
      return;
    }
    if (mode === "signup") {
      const passwordProblem = validatePassword(password);
      if (passwordProblem) {
        setError(passwordProblem);
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
    }

    setBusy(true);
    try {
      const address = email.trim();
      const result =
        mode === "signin" ? await signIn(address, password) : mode === "signup" ? await signUp(address, password) : await resetPassword(address);
      setError(result.error);
      setNotice(result.notice);
      if (!result.error) {
        setPassword("");
        setConfirm("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel settings" onSubmit={submit} noValidate>
      <div>
        <p className="eyebrow">Account</p>
        <h2>{TITLES[mode]}</h2>
        <p className="muted">
          {mode === "forgot"
            ? "Enter your email and we'll send a link to choose a new password."
            : "An account is optional. Every film feature works without one."}
        </p>
      </div>

      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={254} required />
      </label>

      {mode !== "forgot" && (
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            minLength={mode === "signup" ? MIN_PASSWORD : undefined}
            required
          />
          {mode === "signup" && <span className="muted small">At least {MIN_PASSWORD} characters.</span>}
        </label>
      )}

      {mode === "signup" && (
        <label>
          Confirm password
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
        </label>
      )}

      <ErrorNote message={error} />
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <div className="row">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Please wait…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
        </button>
      </div>

      <p className="muted small">
        {mode === "signin" && (
          <>
            <button className="link" type="button" onClick={() => switchMode("signup")}>
              Create an account
            </button>
            <button className="link" type="button" onClick={() => switchMode("forgot")}>
              Forgot password?
            </button>
          </>
        )}
        {mode !== "signin" && (
          <button className="link" type="button" onClick={() => switchMode("signin")}>
            Back to sign in
          </button>
        )}
      </p>
    </form>
  );
}

function SetPassword() {
  const { updatePassword } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const problem = validatePassword(password);
    if (problem) {
      setError(problem);
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await updatePassword(password);
      setError(result.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel settings" onSubmit={submit} noValidate>
      <div>
        <p className="eyebrow">Account</p>
        <h2>Choose a new password</h2>
        <p className="muted">You opened a password-reset link. Pick a new password to finish.</p>
      </div>
      <label>
        New password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
        <span className="muted small">At least {MIN_PASSWORD} characters.</span>
      </label>
      <label>
        Confirm new password
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
      </label>
      <ErrorNote message={error} />
      <div className="row">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save password"}
        </button>
      </div>
    </form>
  );
}

const formatDate = (iso: string | undefined) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";

function Profile() {
  const { user, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!user) return null;

  const leave = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setError((await signOut()).error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel settings">
      <div>
        <p className="eyebrow">Account</p>
        <h2>Your profile</h2>
      </div>
      <dl className="profile">
        <dt>Email</dt>
        <dd>{user.email ?? "—"}</dd>
        <dt>Email verified</dt>
        <dd>{user.email_confirmed_at ? "Yes" : "Not yet"}</dd>
        <dt>Member since</dt>
        <dd>{formatDate(user.created_at)}</dd>
        <dt>Last sign-in</dt>
        <dd>{formatDate(user.last_sign_in_at)}</dd>
      </dl>
      <ErrorNote message={error} />
      <div className="row">
        <button className="ghost" type="button" disabled={busy} onClick={() => void leave()}>
          {busy ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
  );
}

/** The account page doubles as the sign-in gate: signed-out visitors see the forms, signed-in users see their profile. */
export function Account() {
  const { configured, loading, user, recovery } = useAuth();

  if (!configured) {
    return (
      <div className="panel settings">
        <div>
          <p className="eyebrow">Account</p>
          <h2>Accounts are not set up</h2>
          <p className="muted">Sign-in isn't available on this deployment. Every other CineCritic feature works without an account.</p>
        </div>
      </div>
    );
  }
  if (loading) return <Loading text="Checking your session…" />;
  if (user && recovery) return <SetPassword />;
  return user ? <Profile /> : <AuthForm />;
}
