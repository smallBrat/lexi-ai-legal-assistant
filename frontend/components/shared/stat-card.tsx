import { Card } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
}): React.JSX.Element {
  return (
    <Card className="flex flex-col gap-2">
      <span className="flex items-center gap-2 text-on-surface-variant">
        <Icon size={18} aria-hidden />
        <span className="lexi-eyebrow">{label}</span>
      </span>
      <span className="font-headline-lg text-headline-lg text-on-surface">{value}</span>
      {hint ? <span className="font-label-sm text-label-sm text-on-surface-variant">{hint}</span> : null}
    </Card>
  );
}
