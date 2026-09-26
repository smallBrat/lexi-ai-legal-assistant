import { Card } from "@/components/ui/card";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Badge } from "@/components/ui/badge";
import type { ClauseAnalysis } from "@/types";

export function ClauseCard({ clause }: { clause: ClauseAnalysis }): React.JSX.Element {
  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="lexi-code">{clause.category}</p>
          <h3 className="font-headline-sm text-headline-sm text-on-surface">{clause.title}</h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="neutral">Importance {clause.importance_score}/100</Badge>
          <RiskBadge level={clause.risk_level} />
        </div>
      </div>
      <p className="font-body-md text-body-md text-on-surface leading-relaxed rounded-lg bg-surface-container-low/60 p-3">
        {clause.original_text}
      </p>
      <p className="font-body-md text-body-md text-on-surface">
        <strong>Plain English: </strong>
        {clause.simplified_text}
      </p>
      <p className="font-label-md text-label-md text-on-surface-variant">
        <strong className="text-on-surface">Why it matters: </strong>
        {clause.why_it_matters}
      </p>
    </Card>
  );
}
