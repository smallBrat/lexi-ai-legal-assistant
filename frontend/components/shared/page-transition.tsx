"use client";

import { domAnimation, LazyMotion, m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

// STATIC IMPORT FIX: The previous dynamic import
// `() => import("framer-motion").then((mod) => mod.domAnimation)`
// caused silent webpack compilation crashes on Windows during 404 route
// compilation. The dynamic import would fail silently when the module
// wasn't already loaded, triggering process exit without error.
// Static import ensures the feature bundle is always available.
export function PageTransition({ children }: { children: ReactNode }): React.JSX.Element {
  const reduce = useReducedMotion();
  if (reduce) return <>{children}</>;
  return (
    <LazyMotion features={domAnimation} strict>
      <m.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: "easeOut" }}>
        {children}
      </m.div>
    </LazyMotion>
  );
}
