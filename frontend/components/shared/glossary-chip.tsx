import type { GlossaryItem } from "@/types";

export function GlossaryChip({ item }: { item: GlossaryItem }): React.JSX.Element {
  return (
    <div className="rounded-xl border border-outline-variant/50 bg-surface-container-lowest p-4">
      <p className="font-label-md text-label-md font-semibold text-primary">{item.term}</p>
      <p className="font-body-md text-body-md text-on-surface-variant mt-1">{item.definition}</p>
    </div>
  );
}
