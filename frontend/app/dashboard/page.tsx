"use client";

import Link from "next/link";
import { useMemo } from "react";
import { AlertTriangle, FileText, Plus, ShieldCheck } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { DocumentCard } from "@/components/shared/document-card";
import { EmptyState } from "@/components/shared/empty-state";
import { PageTransition } from "@/components/shared/page-transition";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocuments } from "@/hooks/use-lexi";

export default function DashboardPage(): React.JSX.Element {
  const { data, isLoading } = useDocuments();
  const docs = useMemo(() => data ?? [], [data]);

  const stats = useMemo(() => {
    const ready = docs.filter((d) => d.status === "ready");
    const avg = ready.length > 0 ? Math.round(ready.reduce((n, d) => n + d.riskScore, 0) / ready.length) : 0;
    return { total: docs.length, flags: docs.reduce((n, d) => n + d.flags, 0), avg };
  }, [docs]);

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Document Dashboard" }]} />
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Document Dashboard</h1>
              <p className="font-body-md text-on-surface-variant">Every document, risk-scored and ready to explore.</p>
            </div>
            <Link href="/upload" className="lexi-btn-primary">
              <Plus size={18} aria-hidden /> New analysis
            </Link>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <StatCard icon={FileText} label="Documents" value={isLoading ? "…" : String(stats.total)} hint="Across contracts, leases & policies" />
            <StatCard icon={AlertTriangle} label="Open flags" value={isLoading ? "…" : String(stats.flags)} hint="Clauses worth a second look" />
            <StatCard icon={ShieldCheck} label="Avg. risk" value={isLoading ? "…" : `${stats.avg}/100`} hint="Lower is calmer" />
          </div>

          <h2 className="mt-8 font-headline-md text-headline-md text-on-surface">Recent documents</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2" aria-busy={isLoading} aria-label={isLoading ? "Loading documents" : "Recent documents"}>
            {isLoading
              ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)
              : docs.map((doc) => <DocumentCard key={doc.id} doc={doc} />)}
          </div>
          {!isLoading && docs.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                icon={FileText}
                title="No documents yet"
                body="Upload your first contract and Lexi will break it down in plain English."
                action={<Link href="/upload" className="lexi-btn-primary">Upload a document</Link>}
              />
            </div>
          ) : null}
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
