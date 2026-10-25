import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Only the project URL and the publishable key belong in the browser.
// Never put a secret / service-role key in a VITE_* variable: Vite ships those to every visitor.
const url = import.meta.env.VITE_SUPABASE_URL?.trim() ?? "";
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() ?? "";

export const supabaseConfigured = url !== "" && key !== "";

// When the variables are missing the app still works; sign-in is simply unavailable.
export const supabase: SupabaseClient | null = supabaseConfigured
  ? createClient(url, key, {
      auth: {
        // PKCE returns a ?code= query parameter instead of #access_token fragments,
        // which would collide with this app's #/page hash routing.
        flowType: "pkce",
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
