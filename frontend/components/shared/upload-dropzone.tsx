"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CloudUpload } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { useUpload } from "@/hooks/use-lexi";
import { ACCEPTED_FILE_TYPES, MAX_UPLOAD_SIZE } from "@/services/upload";

export function UploadDropzone({ compact = false }: { compact?: boolean }): React.JSX.Element {
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUpload();

  useEffect(() => () => setProgress(null), []);

  const selectFile = useCallback((file: File) => {
    setError(null);
    if (!ACCEPTED_FILE_TYPES.includes(file.type) || file.size > MAX_UPLOAD_SIZE) {
      setError("Choose a PDF, DOCX, PNG, JPG, or JPEG smaller than 20 MB.");
      return;
    }
    setProgress(0);
    upload.mutate({ file, documentType: "other", onProgress: setProgress }, {
      onSuccess: (result) => router.push(`/processing?doc=${result.document_id}`),
      onError: (cause) => { setProgress(null); setError(cause.message); },
    });
  }, [router, upload]);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload a legal document. Press Enter to select a file."
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
        "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-surface-container-lowest text-center transition-colors",
        compact ? "p-8" : "p-12",
        dragging ? "border-primary bg-primary-fixed/40" : "border-outline-variant hover:border-primary"
        )}
      >
        <input ref={inputRef} type="file" className="hidden" accept={ACCEPTED_FILE_TYPES.join(",")} onClick={(e) => e.stopPropagation()} onChange={(e) => e.target.files?.[0] && selectFile(e.target.files[0])} />
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-fixed text-primary">
        <CloudUpload size={26} aria-hidden />
      </span>
      <p className="mt-4 font-headline-sm text-headline-sm text-on-surface">
        Drag & drop your document, or <span className="text-primary underline">browse files</span>
      </p>
      <p className="mt-1 font-body-md text-body-md text-on-surface-variant">
        PDF, DOCX, or photos of paper contracts • 256-bit encrypted • Zero-retention
      </p>
      {progress !== null ? (
        <div className="mt-6 w-full max-w-md space-y-2">
          <Progress value={progress} />
          <p className="lexi-code" aria-live="polite">
            {progress < 100 ? `Uploading… ${Math.round(progress)}%` : "Upload complete — analyzing…"}
          </p>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-4 font-label-md text-error">{error}</p> : null}
    </div>
  );
}
