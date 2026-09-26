// Test-only Supabase stub: resolves "@/lib/supabase" to this file so the
// real api-client can run under node. The session token is controllable via
// `setStubSession`.
let accessToken = "test-token-abc";

export function setStubSession(token) {
  accessToken = token;
}

export function getSupabaseBrowserClient() {
  return {
    auth: {
      getSession: async () => ({
        data: accessToken ? { session: { access_token: accessToken } } : { session: null },
      }),
      refreshSession: async () => ({
        data: accessToken ? { session: { access_token: accessToken } } : { session: null },
      }),
    },
  };
}
