"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeftRight, FileDiff, History, WifiOff } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageTransition } from "@/components/shared/page-transition";
import { PageHeader } from "@/components/shared/page-header";
import { CompareUploadCard, type CompareSlotStatus } from "@/components/compare/compare-upload-card";
import { listComparisons } from "@/services/compare";
import { loadCompareSession, clearCompareSession, saveCompareSession } from "@/lib/compare-session";
import { pollingRegistry } from "@/lib/polling-registry";

export default function ComparePage(): React.JSX.Element {
  const router = useRouter();
  const [docA, setDocA] = useState<string | null>(null);
  const [docB, setDocB] = useState<string | null>(null);
  const [readyA, setReadyA] = useState(false);
  const [readyB, setReadyB] = useState(false);
  const [hasNetworkError, setHasNetworkError] = useState(false);

  // Restore session from sessionStorage on mount
  useEffect(() => {
    const session = loadCompareSession();
    if (session) {
      if (session.documentAId) {
        setDocA(session.documentAId);
        if (session.readyA) setReadyA(true);
      }
      if (session.documentBId) {
        setDocB(session.documentBId);
        if (session.readyB) setReadyB(true);
      }
    }
  }, []);

  const onStatusChange = useCallback((slot: "A" | "B", _status: CompareSlotStatus, ready: boolean) => {
    if (slot === "A") setReadyA(ready);
    else setReadyB(ready);
  }, []);

  const { data: history } = useQuery({
    queryKey: ["comparisons"],
    queryFn: () => listComparisons(10),
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  // Check if either document has polling errors
  useEffect(() => {
    const checkErrors = () => {
      const aError = docA ? pollingRegistry.getError(docA) : null;
      const bError = docB ? pollingRegistry.getError(docB) : null;
      setHasNetworkError(Boolean(aError || bError));
    };
    checkErrors();
    const interval = setInterval(checkErrors, 5000);
    return () => clearInterval(interval);
  }, [docA, docB]);

  // Phase 14.1 req. 6: the old "auto-resume" effect that called
  // pollingRegistry.setStatus(id, "polling") directly was REMOVED — bare
  // status mutation is forbidden (it bypasses the duplicate-start guard and
  // can resurrect a stopped loop). Each upload card's useDocument →
  // usePolling → startFresh() is the single owner of polling state; this
  // page only reads statuses via useDocument's returned data.

  const distinct = docA != null && docB != null && docA !== docB;
  const canCompare = readyA && readyB && distinct;
  const resultsHref = distinct ? `/compare/results?a=${docA}&b=${docB}` : "/compare/results";

  const handleCompare = useCallback(() => {
    if (canCompare) {
      clearCompareSession();
    }
  }, [canCompare]);

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compare Documents" }]} />
          <PageHeader icon={ArrowLeftRight} title="Compare Documents" subtitle="Upload two versions — Lexi diffs every clause." />

          {hasNetworkError ? (
            <div className="mt-4 flex items-center gap-2 p-3 rounded-xl bg-warning-container/10 border border-warning/30 text-warning font-label-md" role="alert">
              <WifiOff size={16} aria-hidden />
              Connection issue detected — polling will automatically reconnect when the network is restored.
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <CompareUploadCard
              slot="A"
              eyebrow="Version A"
              documentId={docA}
              otherDocumentId={docB}
              onSelect={(id) => {
                setDocA(id);
                saveCompareSession({ documentAId: id });
              }}
              onClear={() => {
                setDocA(null);
                setReadyA(false);
              }}
              onStatusChange={onStatusChange}
            />
            <CompareUploadCard
              slot="B"
              eyebrow="Version B"
              documentId={docB}
              otherDocumentId={docA}
              onSelect={(id) => {
                setDocB(id);
                saveCompareSession({ documentBId: id });
              }}
              onClear={() => {
                setDocB(null);
                setReadyB(false);
              }}
              onStatusChange={onStatusChange}
            />
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            {canCompare ? (
              <Link href={resultsHref} className="lexi-btn-primary" aria-disabled="false" onClick={handleCompare}>
                <FileDiff size={18} aria-hidden /> Run comparison
              </Link>
            ) : (
              <span className="lexi-btn-primary opacity-50" aria-disabled="true" title="Both documents must finish analysis first">
                <FileDiff size={18} aria-hidden /> Run comparison
              </span>
            )}
            {!canCompare ? (
              <p className="font-body-md text-on-surface-variant" aria-live="polite">
                {docA == null || docB == null
                  ? "Upload both documents to enable comparison."
                  : !distinct
                    ? "Select two different documents."
                    : "Waiting for analysis to finish on both documents…"}
              </p>
            ) : null}
          </div>

          {/* State machine indicator */}
          <div className="mt-4 flex items-center gap-2 font-label-md text-on-surface-variant" aria-live="polite">
            <StateIndicator label="Upload" active={docA != null || docB != null} />
            <span className="text-on-surface-variant/30">→</span>
            <StateIndicator label="OCR" active={(readyA || readyB) && !canCompare} />
            <span className="text-on-surface-variant/30">→</span>
            <StateIndicator label="Analyze" active={!readyA || !readyB} />
            <span className="text-on-surface-variant/30">→</span>
            <StateIndicator label="Ready" active={readyA && readyB} />
          </div>

          {history != null && history.length > 0 ? (
            <section className="mt-8" aria-label="Recent comparisons">
              <h2 className="flex items-center gap-2 font-headline-sm text-headline-sm text-on-surface">
                <History size={18} className="text-primary" aria-hidden /> Recent comparisons
              </h2>
              <ul className="mt-3 space-y-2">
                {history.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="lexi-card w-full p-4 text-left transition-colors hover:border-primary"
                      onClick={() => {
                        clearCompareSession();
                        router.push(`/compare/results?a=${item.document_a_id}&b=${item.document_b_id}`);
                      }}
                    >
                      <span className="lexi-code">
                        {item.document_a_id.slice(0, 8)}… vs {item.document_b_id.slice(0, 8)}…
                      </span>
                      <span className="ml-3 font-body-md text-on-surface-variant">
                        {new Date(item.created_at).toLocaleString()} — similarity{" "}
                        {item.result.metrics?.similarity_score ?? "—"}%
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </main>
      </PageTransition>
    </DashboardShell>
  );
}

function StateIndicator({ label, active }: { label: string; active: boolean }): React.JSX.Element {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-label-md ${active ? "bg-primary-container text-on-primary-container" : "bg-surface-container-high text-on-surface-variant"}`}>
      {label}
    </span>
  );
}
