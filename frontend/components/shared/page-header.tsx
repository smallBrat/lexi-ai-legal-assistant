import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  action?: ReactNode;
}

/** Standard icon + title + subtitle page header shared by workspace pages. */
export function PageHeader({ icon: Icon, title, subtitle, action }: PageHeaderProps): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-on-primary">
          <Icon size={20} aria-hidden />
        </span>
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface">{title}</h1>
          <p className="font-body-md text-on-surface-variant">{subtitle}</p>
        </div>
      </div>
      {action}
    </div>
  );
}
