"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeftRight,
  Bell,
  BookMarked,
  LayoutDashboard,
  Menu,
  Scale,
  Settings,
  UploadCloud,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/shared/logo";
import { useAuth } from "@/contexts/auth-context";

type NavItem = {
  id: string;
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
};

// Canonical sidebar navigation: every item has a unique `id` (used as the
// React key), every href is unique, and active detection uses the pathname.
// The old "Clause Explorer" entry pointed at the same "/dashboard" href as
// the Dashboard entry, which produced duplicate React keys ("/dashboard")
// and two identically-highlighted links. Clause exploration lives inside
// the document detail tabs, so the duplicate entry is removed rather than
// re-pointed at a demo document id (which would auto-fire POST /analyze).
const NAV: NavItem[] = [
  { id: "dashboard-home", label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { id: "upload-new", label: "Upload", href: "/upload", icon: UploadCloud },
  { id: "compare-docs", label: "Compare", href: "/compare", icon: ArrowLeftRight },
  { id: "rights-guide", label: "Know Your Rights", href: "/rights", icon: Scale },
  { id: "saved-docs", label: "Saved", href: "/saved", icon: BookMarked },
  { id: "settings", label: "Settings", href: "/settings", icon: Settings },
];

export function DashboardShell({ children }: { children: React.ReactNode }): React.JSX.Element {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { user, signOut } = useAuth();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const sidebar = (
    <nav aria-label="Dashboard" className="flex flex-col gap-1 p-4">
      {NAV.map((item) => {
        const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
        const Icon = item.icon;
        return (
          <Link
            key={item.id}
            href={item.href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-[44px] items-center gap-3 rounded-xl px-4 py-2.5 font-label-md transition-colors",
              active ? "bg-primary-fixed text-on-primary-fixed font-semibold" : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
            )}
          >
            <Icon size={18} aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-surface">
      <header className="sticky top-0 z-40 border-b border-outline-variant/40 bg-surface-container-lowest/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-4 md:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="flex h-[44px] w-[44px] items-center justify-center rounded-xl hover:bg-surface-container md:hidden"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
            <Logo />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Notifications"
              className="flex h-[44px] w-[44px] items-center justify-center rounded-xl text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
            >
              <Bell size={19} aria-hidden />
            </button>
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-container font-label-md text-on-primary"
              aria-label="Sign out"
              title={user?.email ?? "Sign out"}
              onClick={() => void signOut()}
            >
              {(user?.email?.[0] ?? "A").toUpperCase()}
            </button>
          </div>
        </div>
      </header>

      {open ? (
        <div className="fixed inset-0 z-30 bg-black/20 md:hidden" onClick={() => setOpen(false)} aria-hidden />
      ) : null}

      <div className="mx-auto flex max-w-[1400px] items-start gap-6 px-4 md:px-8 py-6">
        <aside
          className={cn(
            "w-64 shrink-0 rounded-2xl border border-outline-variant/40 bg-surface-container-lowest shadow-card",
            "fixed z-40 left-4 top-20 max-h-[calc(100vh-6rem)] overflow-auto md:static md:block",
            open ? "block" : "hidden"
          )}
        >
          {sidebar}
          <div className="m-4 rounded-xl bg-surface-container-low p-4">
            <p className="font-label-md font-semibold text-on-surface">Attorney pack ready</p>
            <p className="mt-1 font-label-sm text-on-surface-variant">4 questions drafted for your MSA review.</p>
            <Link href="/report" className="mt-3 inline-flex min-h-[44px] items-center font-label-md text-primary hover:underline">
              Open export report →
            </Link>
          </div>
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
