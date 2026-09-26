import { Scale } from "lucide-react";
import Link from "next/link";

export function Logo({ compact = false }: { compact?: boolean }): React.JSX.Element {
  return (
    <Link href="/" className="flex items-center gap-2 rounded-lg" aria-label="Lexi home">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-on-primary">
        <Scale size={20} aria-hidden />
      </span>
      {!compact ? <span className="font-headline-sm text-headline-sm font-semibold tracking-tight text-on-surface">Lexi</span> : null}
    </Link>
  );
}
