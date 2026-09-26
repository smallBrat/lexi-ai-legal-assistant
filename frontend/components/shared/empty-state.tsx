import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  action?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-outline-variant bg-surface-container-lowest px-6 py-14 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-container text-on-surface-variant">
        <Icon size={26} aria-hidden />
      </span>
      <h3 className="mt-4 font-headline-sm text-headline-sm text-on-surface">{title}</h3>
      <p className="mt-1 max-w-md font-body-md text-body-md text-on-surface-variant">{body}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
