import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function NotFound(): React.JSX.Element {
  return (
    <main className="min-h-screen bg-surface flex items-center justify-center p-6">
      <div className="w-full max-w-lg rounded-2xl bg-surface-container-lowest p-8 shadow-card border border-outline-variant/40 text-center">
        <h1 className="mt-4 font-headline-lg text-headline-lg text-on-surface">Page Not Found</h1>
        <p className="mt-2 font-body-md text-on-surface-variant">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link href="/" className="mt-6 inline-flex min-h-[44px] items-center gap-1 font-label-md text-primary hover:underline">
          <ArrowLeft size={18} aria-hidden /> Go back home
        </Link>
      </div>
    </main>
  );
}
