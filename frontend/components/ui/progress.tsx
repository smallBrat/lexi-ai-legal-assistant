import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }): React.JSX.Element {
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className={cn("w-full bg-surface-container rounded-full h-1.5 overflow-hidden", className)}
    >
      <div
        className="bg-primary h-1.5 rounded-full transition-all"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
