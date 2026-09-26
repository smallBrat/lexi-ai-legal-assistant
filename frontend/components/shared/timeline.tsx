import { CalendarClock } from "lucide-react";
import type { TimelineItem } from "@/types";

export function Timeline({ items }: { items: TimelineItem[] }): React.JSX.Element {
  return (
    <ol className="relative space-y-5 border-l border-outline-variant/60 pl-6" aria-label="Document timeline">
      {items.map((item) => (
        <li key={`${item.date}-${item.event}`} className="relative">
          <span
            aria-hidden
            className="absolute -left-[31px] top-0 flex h-4 w-4 items-center justify-center rounded-full bg-primary-fixed"
          >
            <CalendarClock size={10} className="text-primary" />
          </span>
          <p className="lexi-code">{item.date}</p>
          <p className="font-label-md text-label-md font-semibold text-on-surface">{item.event}</p>
          <p className="font-label-sm text-label-sm text-on-surface-variant">{item.description}</p>
        </li>
      ))}
    </ol>
  );
}
