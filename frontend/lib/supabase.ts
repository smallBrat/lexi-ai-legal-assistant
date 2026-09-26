import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let browserClient: SupabaseClient | undefined;

export function getSupabaseBrowserClient(): SupabaseClient {
  if (browserClient) return browserClient;

  if (typeof window === "undefined") {
    // During SSR we cannot create a Supabase client because it
    // depends on window/localStorage. Return a thrower function
    // that only activates if anything actually tries to use it.
    // The getAccessToken() caller in api-client.ts already guards
    // with typeof window === "undefined" and returns null before
    // reaching this function, so this branch is defensive only.
    const noOpClient = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321",
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "dummy",
      { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } }
    );
    return noOpClient;
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error("Supabase environment variables are missing.");
  }

  browserClient = createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return browserClient;
}
