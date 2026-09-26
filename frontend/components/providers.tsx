"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect, useState, type ReactNode } from "react";
import { AuthProvider } from "@/contexts/auth-context";
import { PollingProvider } from "@/components/compare/polling-provider";

export function Providers({ children }: { children: ReactNode }): React.JSX.Element {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
            // Never retry indefinitely: a retry loop against a slow
            // POST /analyze or a failing chat endpoint kept the dev server
            // and HMR websocket busy and masked the real error.
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
          },
          mutations: { retry: 0 },
        },
      })
  );

  // Expose the query cache for development debugging via browser console.
  useEffect(() => {
    if (process.env.NODE_ENV !== "development" || typeof window === "undefined") return;
    (window as unknown as { __LEXI_QUERY_CACHE__?: unknown }).__LEXI_QUERY_CACHE__ = client.getQueryCache();
  }, [client]);

  // Ensure QueryClient is properly disposed on unmount
  useEffect(() => {
    return () => {
      // Cleanup is handled by React Query's automatic cancellation
      // but we explicitly cancel any pending queries on unmount
      client.cancelQueries({ queryKey: ["documents"], exact: true }).catch(() => {});
      client.cancelQueries({ queryKey: ["document"], exact: true }).catch(() => {});
    };
  }, [client]);

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <PollingProvider>
          <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
            {children}
          </ThemeProvider>
        </PollingProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
