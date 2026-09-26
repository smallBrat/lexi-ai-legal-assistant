"use client";

import { BookOpenText, Clock3 } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageTransition } from "@/components/shared/page-transition";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useRights } from "@/hooks/use-lexi";

export default function RightsPage(): React.JSX.Element {
  const { data, isLoading } = useRights();

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Know Your Rights" }]} />
          <h1 className="font-headline-lg text-headline-lg text-on-surface">Know Your Rights</h1>
          <p className="mt-1 font-body-md text-on-surface-variant">
            Plain-English guides to housing, work, contracts, and insurance — general information, not legal advice.
          </p>
          <div className="mt-6 grid gap-4 md:grid-cols-2" aria-busy={isLoading} aria-label={isLoading ? "Loading guides" : "Rights guides"}>
            {isLoading
              ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)
              : (data ?? []).map((a) => (
                <article key={a.id} className="lexi-card lexi-card-hover p-6">
                  <div className="flex items-center gap-2">
                    <BookOpenText size={18} className="text-primary" aria-hidden />
                    <Badge tone="info">{a.category}</Badge>
                    <span className="ml-auto flex items-center gap-1 font-label-sm text-on-surface-variant">
                      <Clock3 size={14} aria-hidden /> {a.readMinutes} min
                    </span>
                  </div>
                  <h2 className="mt-3 font-headline-sm text-headline-sm text-on-surface">{a.title}</h2>
                  <p className="mt-1 font-body-md text-on-surface-variant">{a.summary}</p>
                  <p className="lexi-code mt-3">{a.jurisdiction}</p>
                </article>
              ))}
          </div>
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
