import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, FileText, Lock, Scale, ShieldCheck } from "lucide-react";
import { SiteFooter, SiteHeader } from "@/components/layout/site-header";
import { PageTransition } from "@/components/shared/page-transition";
import { Progress } from "@/components/ui/progress";

export default function LandingPage(): React.JSX.Element {
  return (
    <PageTransition>
      <SiteHeader />
      <main id="main" className="w-full pt-16 bg-surface min-h-screen">
        <section className="w-full max-w-7xl mx-auto px-8 pt-12 pb-20">
          <div className="flex flex-col items-center text-center max-w-4xl mx-auto">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-container-low text-on-surface-variant font-label-sm mb-6">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" aria-hidden />
              <span>Zero-Retention Architecture • SOC-2 Type II Certified</span>
            </div>
            <h1 className="font-display-hero text-display-hero-mobile md:text-display-hero text-on-surface tracking-tight max-w-3xl">
              Understand legal documents without the legal jargon.
            </h1>
            <p className="font-body-lg text-body-lg text-on-secondary-container mt-6 max-w-2xl leading-relaxed">
              Upload contracts, rental agreements, policies, insurance documents, employment letters,
              and government notices. Lexi explains what matters, highlights risks, and helps you
              prepare for professional legal advice.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-4 mt-8">
              <Link href="/upload" className="lexi-btn-primary">
                <FileText size={18} aria-hidden /> Analyze a Document
              </Link>
              <Link href="/dashboard" className="lexi-btn-secondary">
                <Eye size={18} aria-hidden /> View Demo
              </Link>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-6 mt-10 text-on-surface-variant font-label-sm">
              <span className="flex items-center gap-1.5"><Lock size={16} className="text-tertiary" aria-hidden /> End-to-end 256-bit encrypted</span>
              <span className="flex items-center gap-1.5"><ShieldCheck size={16} className="text-primary" aria-hidden /> Clause-level exact verification</span>
              <span className="flex items-center gap-1.5"><Scale size={16} aria-hidden /> Built for attorney collaboration</span>
            </div>
          </div>

          {/* Workbench preview — mirrors Stitch hero mockup */}
          <div className="mt-16 w-full rounded-xl bg-surface-container-lowest shadow-xl overflow-hidden" id="workbench-preview">
            <div className="flex flex-wrap items-center justify-between px-6 py-3.5 bg-surface-container-low gap-3">
              <div className="flex items-center gap-3">
                <FileText size={18} className="text-primary" aria-hidden />
                <span className="font-code font-medium text-on-surface">Master_Services_IP_Licensing_Agreement_v2.pdf</span>
                <span className="px-2 py-0.5 rounded-full bg-surface-variant font-code text-[11px] text-on-surface-variant">42 KB • Page 4 of 18</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-lowest text-tertiary font-label-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-tertiary" aria-hidden /> Analysis Complete
                </span>
                <span className="font-code text-on-surface-variant">Parsed in 1.4s</span>
              </div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[420px]">
              <div className="lg:col-span-4 bg-surface-container-low p-5 space-y-5">
                <div>
                  <p className="lexi-eyebrow">Risk Scorecard</p>
                  <div className="mt-2 p-3.5 rounded-lg bg-surface-container-lowest shadow-card">
                    <div className="flex items-center justify-between">
                      <span className="font-headline-sm font-semibold text-on-surface">Moderate</span>
                      <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-surface font-code text-[11px]">Score: 68/100</span>
                    </div>
                    <p className="font-label-sm text-on-surface-variant mt-1.5">3 flags detected across 48 clauses.</p>
                    <Progress value={62} className="mt-3" />
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="lexi-eyebrow">Detected Flags</p>
                  {["Termination rights", "Payment obligations", "Liability limits"].map((title) => (
                    <div key={title} className="p-2.5 rounded-lg bg-surface-container-lowest shadow-card flex items-start gap-2.5">
                      <CheckCircle2 size={18} className="text-primary shrink-0 mt-0.5" aria-hidden />
                      <div className="min-w-0">
                        <p className="font-label-md font-semibold text-on-surface truncate">{title}</p>
                        <p className="font-label-sm text-on-surface-variant truncate">Detected clause</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="lg:col-span-8 bg-surface-container-lowest p-6">
                <p className="lexi-eyebrow">Source contract excerpt</p>
                <p className="mt-3 font-body-md text-on-surface leading-relaxed p-4 rounded-lg bg-surface-container-low/60">
                  “Either party may terminate this Agreement without cause by providing not less than
                  thirty (30) days prior written notice…”
                </p>
                <div className="mt-4 rounded-xl bg-primary-fixed/40 p-4">
                  <p className="font-label-md font-semibold text-on-primary-fixed">Lexi plain-English take</p>
                  <p className="mt-1 font-body-md text-on-surface">Upload a document to receive a grounded plain-English analysis from Lexi.</p>
                  <Link href="/upload" className="mt-3 inline-flex min-h-[44px] items-center gap-1 font-label-md text-primary hover:underline">
                    Try it on your document <ArrowRight size={16} aria-hidden />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="max-w-7xl mx-auto px-8 pb-16 grid gap-4 md:grid-cols-3">
          {[
            { title: "Clause Explorer", body: "Every risky clause, quoted exactly, then rewritten in plain English with why-it-matters notes." },
            { title: "AI Chat with citations", body: "Ask anything about your document. Every answer cites the exact section it came from." },
            { title: "Attorney-ready exports", body: "One-click briefs, timelines, and lawyer questions your counsel will actually thank you for." },
          ].map((f) => (
            <div key={f.title} className="lexi-card p-6">
              <h2 className="font-headline-sm text-on-surface">{f.title}</h2>
              <p className="mt-2 font-body-md text-on-surface-variant">{f.body}</p>
            </div>
          ))}
        </section>

        <section id="how-it-works" className="max-w-7xl mx-auto px-8 pb-20">
          <div className="lexi-card p-8 text-center">
            <h2 className="font-headline-lg text-headline-lg text-on-surface">From upload to attorney-ready in minutes</h2>
            <p className="mt-2 font-body-md text-on-surface-variant">Upload → AI analysis → plain-English review → export.</p>
            <Link href="/upload" className="lexi-btn-primary mt-6">Start free — no signup to preview</Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </PageTransition>
  );
}
