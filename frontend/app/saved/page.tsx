"use client";

import Link from "next/link";
import { BookMarked, Trash2 } from "lucide-react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { DocumentCard } from "@/components/shared/document-card";
import { EmptyState } from "@/components/shared/empty-state";
import { PageTransition } from "@/components/shared/page-transition";
import { useDocuments } from "@/hooks/use-lexi";

export default function SavedPage(): React.JSX.Element {
  const { data } = useDocuments();
  const [removedIds, setRemovedIds] = useState<string[]>([]);
  const docs = (data ?? []).filter((d) => !removedIds.includes(d.id));

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Saved Documents" }]} />
          <h1 className="font-headline-lg text-headline-lg text-on-surface">Saved Documents</h1>
          <p className="mt-1 font-body-md text-on-surface-variant">Your pinned analyses, available offline.</p>
          {docs.length === 0 ? (
            <div className="mt-6">
              <EmptyState
                icon={BookMarked}
                title="Nothing saved yet"
                body="Pin documents from the dashboard to keep them here."
                action={<Link href="/dashboard" className="lexi-btn-primary">Browse documents</Link>}
              />
            </div>
          ) : (
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              {docs.map((doc) => (
                <div key={doc.id} className="relative">
                  <DocumentCard doc={doc} />
                  <button
                    type="button"
                    aria-label={`Remove ${doc.title} from saved`}
                    onClick={() => setRemovedIds((prev) => [...prev, doc.id])}
                    className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-xl text-on-surface-variant hover:bg-error-container hover:text-on-error-container"
                  >
                    <Trash2 size={18} aria-hidden />
                  </button>
                </div>
              ))}
            </div>
          )}
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
