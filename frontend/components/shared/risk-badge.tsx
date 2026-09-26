import { Badge } from "@/components/ui/badge";
import type { RiskLevel } from "@/types";

const label: Record<RiskLevel, string> = { high: "High risk", medium: "Medium risk", low: "Low risk" };

export function RiskBadge({ level }: { level: RiskLevel }): React.JSX.Element {
  return <Badge tone={level}>{label[level]}</Badge>;
}
