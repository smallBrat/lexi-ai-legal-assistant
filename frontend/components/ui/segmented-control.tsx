"use client";

import { cn } from "@/lib/utils";

interface SegmentedControlProps<T extends string> {
  options: readonly T[];
  value: T;
  onChange: (next: T) => void;
  label: string;
  formatLabel?: (option: T) => string;
}

/** Single-select pill group with radiogroup semantics. Used for format + text-size pickers. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  formatLabel = (o) => o,
}: SegmentedControlProps<T>): React.JSX.Element {
  return (
    <div className="flex gap-2" role="radiogroup" aria-label={label}>
      {options.map((option) => {
        const selected = option === value;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option)}
            className={cn(
              "min-h-[44px] flex-1 rounded-xl border px-3 font-label-md capitalize focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
              selected
                ? "border-primary bg-primary-fixed/40 font-semibold text-on-surface"
                : "border-outline-variant text-on-surface-variant"
            )}
          >
            {formatLabel(option)}
          </button>
        );
      })}
    </div>
  );
}
