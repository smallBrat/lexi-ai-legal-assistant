import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

const tones: Record<string, string> = {
  high: "lexi-risk-high",
  medium: "lexi-risk-medium",
  low: "lexi-risk-low",
  info: "bg-primary-fixed text-on-primary-fixed",
  neutral: "bg-surface-container text-on-surface-variant",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }): React.JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-label-sm",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
