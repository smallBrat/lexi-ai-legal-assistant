import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>): React.JSX.Element {
  return <div aria-hidden className={cn("animate-pulse rounded-lg bg-surface-container", className)} {...props} />;
}
