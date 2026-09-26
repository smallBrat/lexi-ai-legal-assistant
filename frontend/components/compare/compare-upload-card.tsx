"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { CheckCircle2, CloudUpload, Loader2, RefreshCw, XCircle, WifiOff } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { isValidDocumentId } from "@/lib/document-id";
import { isAnalysisInFlight, useAnalyzeDocument, useDocument, useUpload } from "@/hooks/use-lexi";
import { ACCEPTED_FILE_TYPES, MAX_UPLOAD_SIZE } from "@/services/upload";
import { saveCompareSession, loadCompareSession } from "@/lib/compare-session";

export type CompareSlotStatus =
  | "idle"
  | "uploading"
  | "ocr_processing"
  | "analysis_processing"
  | "ready"
  | "failed";

const STATUS_LABEL: Record<CompareSlotStatus, string> = {
  idle: "No document selected",
  uploading: "Uploading",
  ocr_processing: "Extracting text",
  analysis_processing: "Analyzing",
  ready: "Ready",
  failed: "Failed",
};

interface CompareUploadCardProps {
  slot: "A" | "B";
  eyebrow: string;
  documentId: string | null;
  otherDocumentId: string | null;
  onSelect: (documentId: string) => void;
  onClear: () => void;
  onStatusChange: (slot: "A" | "B", status: CompareSlotStatus, ready: boolean) => void;
}

export function CompareUploadCard({
  slot,
  eyebrow,
  documentId,
  otherDocumentId,
  onSelect,
  onClear,
  onStatusChange,
}: CompareUploadCardProps): React.JSX.Element {
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [networkError, setNetworkError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const analyzeTriggered = useRef<string | null>(null);
  const pollingErrorRef = useRef<string | null>(null);

  const upload = useUpload();
  const analyze = useAnalyzeDocument();
  const valid = documentId != null && isValidDocumentId(documentId);
  const { data: document, isPolling, pollingError } = useDocument(valid ? (documentId as string) : "");

  // Track polling errors for UI
  useEffect(() => {
    if (pollingError) {
      pollingErrorRef.current = pollingError;
      if (pollingError.includes("Backend busy") || pollingError.includes("timeout")) {
        setNetworkError(true);
      }
    }
    if (!pollingError) {
      pollingErrorRef.current = null;
      setNetworkError(false);
    }
  }, [pollingError]);

  // Restore session from sessionStorage on mount
  useEffect(() => {
    const session = loadCompareSession();
    if (session && slot === "A" && session.documentAId && !documentId) {
      onSelect(session.documentAId);
    } else if (session && slot === "B" && session.documentBId && !documentId) {
      onSelect(session.documentBId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist state to sessionStorage
  useEffect(() => {
    if (documentId) {
      saveCompareSession({
        [`document${slot}Title`]: document?.title ?? null,
        [`document${slot}Status`]: document?.status ?? null,
        [`document${slot}AnalysisPresent`]: document?.analysis != null,
        [`document${slot}Ready`]: document?.status === "ready" && document?.analysis != null,
      });
    }
  }, [documentId, document, slot]);

  // Save session on document changes
  useEffect(() => {
    if (documentId) {
      saveCompareSession({
        [`document${slot}Id`]: documentId,
        [`document${slot}Title`]: document?.title ?? null,
        [`document${slot}Status`]: document?.status ?? null,
        [`document${slot}AnalysisPresent`]: document?.analysis != null,
        [`document${slot}Ready`]: document?.status === "ready" && document?.analysis != null,
      });
    }
  }, [document, slot, documentId]);

  const status: CompareSlotStatus = useMemo(() => {
    if (documentId == null) return "idle";
    if (progress !== null && progress < 100) return "uploading";
    if (!document) return "ocr_processing";
    if (document.status === "failed" || document.status === "analysis_failed") return "failed";
    if (document.analysis != null) return "ready";
    if (document.status === "ready") return "analysis_processing";
    return "ocr_processing";
  }, [documentId, progress, document]);

  const ready = status === "ready";

  // Report readiness to parent.
  useEffect(() => {
    onStatusChange(slot, status, ready);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot, status, ready]);

  // Reset analyze guard when slot changes.
  useEffect(() => {
    if (analyzeTriggered.current !== documentId) {
      analyzeTriggered.current = null;
    }
  }, [documentId]);

  // Fire POST /analyze exactly once when OCR is done but analysis is missing.
  useEffect(() => {
    if (!valid || !document || !documentId) return;
    if (document.status !== "ready" || document.analysis != null) return;
    if (analyzeTriggered.current === documentId || analyze.isPending || isAnalysisInFlight(documentId)) return;
    analyzeTriggered.current = documentId;
    analyze.mutate({ documentId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valid, document?.status, document?.analysis, documentId]);

  // Persist compare session on cleanup
  useEffect(() => {
    return () => {
      if (documentId) {
        saveCompareSession({
          [`document${slot}Id`]: documentId,
          [`document${slot}Title`]: document?.title ?? null,
          [`document${slot}Status`]: document?.status ?? null,
          [`document${slot}AnalysisPresent`]: document?.analysis != null,
          [`document${slot}Ready`]: document?.status === "ready" && document?.analysis != null,
        });
      }
    };
  }, [documentId, document, slot]);

  const selectFile = useCallback(
    (file: File) => {
      setError(null);
      setNetworkError(false);
      if (!ACCEPTED_FILE_TYPES.includes(file.type) || file.size > MAX_UPLOAD_SIZE) {
        setError("Choose a PDF, DOCX, PNG, JPG, or JPEG smaller than 20 MB.");
        return;
      }
      setProgress(0);
      upload.mutate(
        { file, documentType: "other", title: file.name, onProgress: setProgress },
        {
          onSuccess: (result) => {
            setProgress(100);
            analyzeTriggered.current = null;
            onSelect(result.document_id);
          },
          onError: (cause) => {
            setProgress(null);
            setError(cause.message);
          },
        },
      );
    },
    [onSelect, upload],
  );

  const isDuplicate = valid && otherDocumentId != null && documentId === otherDocumentId;

  // Determine error message based on error type
  const errorMessage = useMemo(() => {
    if (error) return error;
    if (networkError) return "Waiting for connection...";
    if (pollingErrorRef.current?.includes("Refreshing session")) return "Refreshing session...";
    if (pollingErrorRef.current?.includes("Backend busy")) return "Backend busy...";
    if (pollingErrorRef.current) return pollingErrorRef.current;
    return null;
  }, [error, networkError]);

  return (
    <section className="lexi-card p-5" aria-label={`Compare document ${slot}`}>
      <div className="flex items-center justify-between">
        <p className="lexi-eyebrow">{eyebrow}</p>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-label-md text-xs font-semibold",
            ready
              ? "bg-tertiary-container text-on-tertiary-container"
              : status === "failed"
                ? "bg-error-container text-on-error-container"
                : status === "idle"
                  ? "bg-surface-container-high text-on-surface-variant"
                  : "bg-primary-container text-on-primary-container",
          )}
          aria-live="polite"
        >
          {status === "ready" ? (
            <CheckCircle2 size={14} aria-hidden />
          ) : status === "failed" ? (
            <XCircle size={14} aria-hidden />
          ) : status !== "idle" ? (
            <Loader2 size={14} className="animate-spin" aria-hidden />
          ) : null}
          {STATUS_LABEL[status]}
          {isPolling && !ready && status !== "failed" && status !== "idle" ? (
            <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          ) : null}
        </span>
      </div>

      {documentId == null ? (
        <div
          role="button"
          tabIndex={0}
          aria-label={`Upload compare document ${slot}. Press Enter to select a file.`}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files[0];
            if (file) selectFile(file);
          }}
          className={cn(
            "mt-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-surface-container-lowest p-8 text-center transition-colors",
            dragging ? "border-primary bg-primary-fixed/40" : "border-outline-variant hover:border-primary",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_FILE_TYPES.join(",")}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              if (e.target.files?.[0]) selectFile(e.target.files[0]);
              e.target.value = "";
            }}
          />
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-fixed text-primary">
            <CloudUpload size={26} aria-hidden />
          </span>
          <p className="mt-4 font-headline-sm text-headline-sm text-on-surface">
            Drag &amp; drop document {slot}, or <span className="text-primary underline">browse files</span>
          </p>
          <p className="mt-1 font-body-md text-body-md text-on-surface-variant">
            PDF, DOCX, or photos of paper contracts • 256-bit encrypted
          </p>
          {progress !== null ? (
            <div className="mt-6 w-full max-w-md space-y-2">
              <Progress value={progress} />
              <p className="lexi-code" aria-live="polite">
                {progress < 100 ? `Uploading… ${Math.round(progress)}%` : "Upload complete — analyzing…"}
              </p>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="mt-4 font-label-md text-error">
              {error}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="mt-3 rounded-2xl bg-surface-container-lowest p-4">
          <p className="truncate font-label-md font-semibold text-on-surface" title={document?.title ?? documentId}>
            {document?.title ?? "Document selected"}
          </p>
          <p className="lexi-code mt-1 break-all">{documentId}</p>
          {status !== "ready" && status !== "failed" ? (
            <div className="mt-3 space-y-2">
              <Progress
                value={
                  status === "uploading"
                    ? progress ?? 5
                    : status === "ocr_processing"
                      ? 40
                      : status === "analysis_processing"
                        ? 75
                        : 0
                }
              />
              <p className="lexi-code" aria-live="polite">
                {errorMessage ?? `${STATUS_LABEL[status]}… this slot stays put while the other document uploads.`}
              </p>
              {isPolling && (
                <p className="lexi-code text-xs text-on-surface-variant" aria-live="polite">
                  Polling active • waiting for analysis…
                </p>
              )}
              {networkError && !errorMessage && (
                <p className="lexi-code text-xs text-warning" aria-live="polite">
                  <WifiOff size={12} className="inline mr-1" /> Connection lost — will auto-reconnect.
                </p>
              )}
            </div>
          ) : null}
          {status === "failed" ? (
            <p role="alert" className="mt-2 font-label-md text-error">
              Analysis failed for this document. Replace it or retry from the dashboard.
            </p>
          ) : null}
          {isDuplicate ? (
            <p role="alert" className="mt-2 font-label-md text-error">
              This document is already selected in the other slot — pick two different documents.
            </p>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="lexi-btn-secondary"
              onClick={() => inputRef.current?.click()}
              disabled={upload.isPending}
            >
              <RefreshCw size={16} aria-hidden /> Replace
            </button>
            <button type="button" className="lexi-btn-ghost" onClick={onClear}>
              Remove
            </button>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept={ACCEPTED_FILE_TYPES.join(",")}
              onChange={(e) => {
                if (e.target.files?.[0]) selectFile(e.target.files[0]);
                e.target.value = "";
              }}
            />
          </div>
          {error ? (
            <p role="alert" className="mt-2 font-label-md text-error">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
