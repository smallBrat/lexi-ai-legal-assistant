"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Briefcase, Download, FileCheck2 } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageHeader } from "@/components/shared/page-header";
import { PageTransition } from "@/components/shared/page-transition";
import { QuestionCard } from "@/components/shared/question-card";
import { Timeline } from "@/components/shared/timeline";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useAnalysis } from "@/hooks/use-lexi";
import { isValidDocumentId } from "@/lib/document-id";

const FORMATS = ["pdf", "docx"] as const;
type ReportFormat = (typeof FORMATS)[number];

function ReportInner(): React.JSX.Element {
  // The report renders analysis for an explicit ?doc=<uuid>. There is no
  // demo document: the previous hardcoded demo-slug query fired
  // POST /analyze/<non-uuid> on every visit, which fails FastAPI UUID path
  // validation with 422 before the handler runs (Gemini never called).
  const params = useSearchParams();
  const docId = params.get("doc") ?? "";
  const valid = isValidDocumentId(docId);
  const { data } = useAnalysis(valid ? docId : "", { enabled: valid });
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [exported, setExported] = useState(false);
  const resetTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    },
    []
  );

  function download(): void {
    setExported(true);
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setExported(false), 3000);
  }

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Dashboard", href: "/dashboard" }, { label: "Export Report" }]} />
          <PageHeader icon={FileCheck2} title="Export Report" subtitle="Attorney-ready brief for your MSA review." />

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <section className="lexi-card p-5" aria-label="Export options">
              <p className="lexi-eyebrow">Format</p>
              <div className="mt-3">
                <SegmentedControl
                  options={FORMATS}
                  value={format}
                  onChange={setFormat}
                  label="Export format"
                  formatLabel={(f) => f.toUpperCase()}
                />
              </div>
              <Button className="mt-4 w-full" onClick={download}>
                <Download size={18} aria-hidden /> Download {format.toUpperCase()}
              </Button>
              {exported ? <p role="status" className="mt-2 font-label-md text-tertiary">Report downloaded — check your files.</p> : null}
              <ul className="mt-4 space-y-1.5 font-body-md text-on-surface-variant">
                <li>• Risk scorecard + all flags</li>
                <li>• Clause-by-clause plain English</li>
                <li>• Timeline & obligations</li>
                <li>• Lawyer questions</li>
              </ul>
            </section>

            <section className="lexi-card p-5 lg:col-span-2" aria-label="Lawyer preparation pack">
              <p className="flex items-center gap-2 font-label-md font-semibold text-on-surface">
                <Briefcase size={18} className="text-primary" aria-hidden /> Lawyer Preparation Pack
              </p>
              <p className="mt-1 font-body-md text-on-surface-variant">
                Bring this to your consultation — it saves roughly 30 minutes of billable review time.
              </p>
              {data ? (
                <>
                  <div className="mt-4 rounded-xl bg-surface-container-low p-4">
                    <p className="lexi-eyebrow">Summary for counsel</p>
                    <p className="mt-1 font-body-md text-on-surface">{data.summary}</p>
                  </div>
                  <ul className="mt-4 space-y-3">
                    {data.questions_for_lawyer.map((q, i) => (
                      <QuestionCard key={q} question={q} index={i} />
                    ))}
                  </ul>
                  <div className="mt-4">
                    <p className="lexi-eyebrow">Critical dates</p>
                    <div className="mt-3"><Timeline items={data.timeline} /></div>
                  </div>
                </>
              ) : !valid ? (
                <p className="mt-4 font-body-md text-on-surface-variant">
                  Select a document first — open this report from a dashboard document so analysis can load.
                </p>
              ) : null}
            </section>
          </div>
        </main>
      </PageTransition>
    </DashboardShell>
  );
}

export default function ReportPage(): React.JSX.Element {
  return (
    <Suspense>
      <ReportInner />
    </Suspense>
  );
}
