import Link from "next/link";
import { Logo } from "@/components/shared/logo";

const links = [
  { href: "/#features", label: "Features" },
  { href: "/#how-it-works", label: "How it Works" },
  { href: "/rights", label: "Know Your Rights" },
  { href: "/auth", label: "Sign In" },
];

export function SiteHeader(): React.JSX.Element {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-surface-container-lowest/90 backdrop-blur-xl shadow-card">
      <div className="h-16 max-w-7xl mx-auto px-4 md:px-8 flex items-center justify-between">
        <Logo />
        <nav className="hidden md:flex items-center gap-6" aria-label="Primary">
          {links.map((l) => (
            <Link
              key={l.label}
              href={l.href}
              className="text-on-surface-variant hover:text-on-surface font-label-md transition-colors"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <Link href="/upload" className="lexi-btn-primary !px-5 !py-2">
            Analyze a Document
          </Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter(): React.JSX.Element {
  return (
    <footer className="border-t border-outline-variant/40 bg-surface-container-low">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="max-w-md">
          <Logo />
          <p className="mt-3 font-body-md text-body-md text-on-surface-variant">
            Lexi explains legal documents in plain English and helps you prepare for professional legal
            advice. Lexi is not a law firm and does not provide legal advice.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-2 font-label-md" aria-label="Footer">
          <Link href="/rights" className="text-on-surface-variant hover:text-on-surface">Know Your Rights</Link>
          <Link href="/compare" className="text-on-surface-variant hover:text-on-surface">Compare</Link>
          <Link href="/report" className="text-on-surface-variant hover:text-on-surface">Export Report</Link>
          <Link href="/settings" className="text-on-surface-variant hover:text-on-surface">Settings</Link>
        </nav>
      </div>
    </footer>
  );
}
