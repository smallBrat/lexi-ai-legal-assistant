import Link from "next/link";
import { ChevronRight } from "lucide-react";

export function Breadcrumbs({ trail }: { trail: { label: string; href?: string }[] }): React.JSX.Element {
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1 font-label-md text-on-surface-variant">
        {trail.map((item, i) => (
          <li key={item.label} className="flex items-center gap-1">
            {i > 0 ? <ChevronRight size={14} aria-hidden /> : null}
            {item.href ? (
              <Link href={item.href} className="hover:text-on-surface hover:underline">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-on-surface font-semibold">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
