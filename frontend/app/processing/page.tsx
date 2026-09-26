"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { FileSearch } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { ProcessingErrorBoundary } from "@/components/shared/error-boundary";
import { isAnalysisInFlight, useAnalyzeDocument, useDocument } from "@/hooks/use-lexi";
import { isValidDocumentId } from "@/lib/document-id";

const STEPS = ["Extracting text", "Detecting clauses", "Scoring risk", "Drafting plain-English summary"];

// Canonical processing lifecycle (single owner of analysis initiation):
//   uploading → ocr_processing → analysis_processing → analysis_complete
//                                                        ↘ analysis_failed
// Polls GET /documents/:id every 3s (via useDocument), fires POST /analyze
// exactly once when OCR is done but analysis is missing, aborts polling on
// terminal states, and navigates to the dashboard only after analysis exists
// (or analysis_failed was persisted).
type ProcessingState =
  | "uploading"
  | "ocr_processing"
  | "analysis_processing"
  | "analysis_failed"
  | "analysis_complete";

function ProcessingInner(): React.JSX.Element {
  const router = useRouter();
  const params = useSearchParams();
  // No demo-id fallback: POST /analyze/<non-uuid> fails FastAPI UUID path
  // validation with 422 before the handler runs. A missing/invalid ?doc=
  // renders an error state instead of emitting a doomed analyze request.
  const doc = params.get("doc") ?? "";
  const docValid = isValidDocumentId(doc);
  // Only poll GET /documents/:id here. Never fetch /chat during processing.
  const { data: document, isError, isPending } = useDocument(docValid ? doc : "");
  const analyze = useAnalyzeDocument();
  const analyzeTriggered = useRef(false);
  const [step, setStep] = useState(0);

  const docState: ProcessingState = isPending || !document
    ? "uploading"
    : document.status === "analysis_failed"
      ? "analysis_failed"
      : document.status === "ready" && document.analysis != null
        ? "analysis_complete"
        : document.status === "ready"
          ? "analysis_processing"
          : "ocr_processing";
  const failed = isError || document?.status === "failed";
  const progress = docState === "analysis_complete" ? 100 : step * 25 + 6;

  useEffect(() => {
    const t = window.setInterval(() => setStep((s) => Math.min(STEPS.length - 1, s + 1)), 2200);
    return () => window.clearInterval(t);
  }, []);

  // Once OCR is done (status ready) but analysis is missing, trigger
  // POST /analyze exactly once — never while another analyze request for
  // this document is already running. The useDocument poll above keeps
  // refreshing until analysis !== null or status becomes analysis_failed.
  useEffect(() => {
    if (!doc || !docValid || isPending || isError || !document) return;
    if (document.status !== "ready" || document.analysis != null) return;
    if (analyzeTriggered.current || analyze.isPending || isAnalysisInFlight(doc)) return;
    analyzeTriggered.current = true;
    analyze.mutate({ documentId: doc });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, document?.status, document?.analysis, isPending, isError]);

  useEffect(() => {
    if (!docValid) return;
    if (docState === "analysis_complete" || docState === "analysis_failed") {
      const t = window.setTimeout(() => router.push(`/dashboard/${doc}`), 300);
      return () => window.clearTimeout(t);
    }
  }, [docState, router, doc, docValid]);

  if (!docValid) {
    return (
      <main id="main" className="min-h-screen bg-surface flex items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-2xl bg-surface-container-lowest p-8 shadow-pop border border-outline-variant/40 text-center" role="alert">
          <h1 className="mt-4 font-headline-lg text-headline-lg text-on-surface">Missing document reference</h1>
          <p className="mt-1 font-body-md text-on-surface-variant">
            This page needs a valid document ID. Please upload a document first — no analysis was requested.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main id="main" className="min-h-screen bg-surface flex items-center justify-center p-6">
      <div className="w-full max-w-lg rounded-2xl bg-surface-container-lowest p-8 shadow-pop border border-outline-variant/40 text-center" aria-busy="true">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-fixed text-primary">
          <FileSearch size={26} aria-hidden className="animate-pulse" />
        </span>
        <h1 className="mt-4 font-headline-lg text-headline-lg text-on-surface">Analyzing your document…</h1>
        <p className="mt-1 font-body-md text-on-surface-variant">
          {failed ? "Analysis failed" : docState === "uploading" ? "Uploading…" : STEPS[step]}
        </p>
        <Progress value={progress} className="mt-6" />
        <p className="lexi-code mt-2">{failed ? "Please return and try again." : `${Math.round(progress)}% • clause-level verification running`}</p>
      </div>
    </main>
  );
}

export default function ProcessingPage(): React.JSX.Element {
  return (
    <Suspense>
      <ProcessingErrorBoundary>
        <ProcessingInner />
      </ProcessingErrorBoundary>
    </Suspense>
  );
}
