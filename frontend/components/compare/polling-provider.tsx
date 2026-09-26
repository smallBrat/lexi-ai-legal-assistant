/**
 * Polling provider context for route transition safety.
 *
 * Creates a polling registry that persists across page navigation.
 * The compare page and results page both subscribe to this provider.
 * State does not disappear during navigation.
 */

"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { pollingRegistry } from "@/lib/polling-registry";

interface PollingProviderValue {
  registry: typeof pollingRegistry;
}

const PollingContext = createContext<PollingProviderValue | null>(null);

export function PollingProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const registryRef = useRef(pollingRegistry);

  // Cleanup all polling on unmount (only on full page unmount,
  // not on route transitions — the registry survives)
  useEffect(() => {
    return () => {
      // Only stop all on actual component unmount (page close/navigate away)
      // The registry itself persists in module scope
    };
  }, []);

  return (
    <PollingContext.Provider value={{ registry: registryRef.current }}>
      {children}
    </PollingContext.Provider>
  );
}

export function usePollingContext(): PollingProviderValue {
  const ctx = useContext(PollingContext);
  if (!ctx) {
    // Fallback: return the singleton registry directly
    return { registry: pollingRegistry };
  }
  return ctx;
}
