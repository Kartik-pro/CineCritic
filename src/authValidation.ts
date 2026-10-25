// Pure helpers for the sign-in forms. No Supabase or DOM imports, so they are easy to test.

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 72; // Supabase hashes passwords with bcrypt, which ignores anything past 72 bytes.

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(value: string): string {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !EMAIL.test(email)) return "Enter a valid email address.";
  return "";
}

export function validatePassword(value: string): string {
  if (value.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (value.length > MAX_PASSWORD) return `Use ${MAX_PASSWORD} characters or fewer.`;
  return "";
}

// Maps Supabase Auth error text to short, user-safe messages. Raw error text is never shown,
// so nothing unexpected (tokens, internal details) can leak into the UI.
export function friendlyAuthError(message: string | undefined): string {
  const text = (message ?? "").toLowerCase();
  if (text.includes("invalid login credentials")) return "Incorrect email or password.";
  if (text.includes("email not confirmed")) return "Please confirm your email first. Check your inbox for the link.";
  if (text.includes("already registered") || text.includes("already been registered")) {
    return "We couldn't create that account. Try signing in instead.";
  }
  if (text.includes("rate limit") || text.includes("only request this after") || text.includes("too many")) {
    return "Too many attempts. Please wait a minute and try again.";
  }
  if (text.includes("different from the old password")) return "Choose a password that is different from your current one.";
  if (text.includes("password should") || text.includes("weak")) return "That password is too weak. Use a longer, less common one.";
  if (text.includes("failed to fetch") || text.includes("network")) return "Network error. Check your connection and try again.";
  return "Something went wrong. Please try again.";
}
