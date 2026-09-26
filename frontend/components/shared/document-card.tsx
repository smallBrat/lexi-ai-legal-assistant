import Link from "next/link";
import { FileText, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { RiskBadge } from "@/components/shared/risk-badge";
import type { LexiDocument } from "@/types";

export function DocumentCard({ doc }: { doc: LexiDocument }): React.JSX.Element {
  return (
    <Link
      href={`/dashboard/${doc.id}`}
      aria-label={`Open ${doc.title}`}
      className="block rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <Card className="lexi-card-hover flex items-start gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
          {doc.status === "processing" ? <Loader2 size={20} className="animate-spin" aria-hidden /> : <FileText size={20} aria-hidden />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-headline-sm text-headline-sm text-on-surface">{doc.title}</span>
          <span className="lexi-code block truncate">
            {doc.fileName} • {doc.pages} pages • {doc.sizeKb} KB
          </span>
          <span className="mt-2 flex flex-wrap items-center gap-2">
            {doc.status === "processing" ? (
              <span className="font-label-sm text-label-sm text-on-surface-variant">Processing…</span>
            ) : (
              <>
                <RiskBadge level={doc.riskLevel} />
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  Score {doc.riskScore}/100 • {doc.flags} flags
                </span>
              </>
            )}
          </span>
        </span>
      </Card>
    </Link>
  );
}
