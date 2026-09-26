"use client";

import { useState } from "react";
import { Accessibility } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageHeader } from "@/components/shared/page-header";
import { PageTransition } from "@/components/shared/page-transition";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";

const TEXT_SIZES = ["standard", "large", "extra"] as const;
type TextSize = (typeof TEXT_SIZES)[number];

export default function SettingsPage(): React.JSX.Element {
  const [plainDefault, setPlainDefault] = useState(true);
  const [fontSize, setFontSize] = useState<TextSize>("standard");
  const [motion, setMotion] = useState(false);

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Settings & Accessibility" }]} />
          <PageHeader
            icon={Accessibility}
            title="Settings & Accessibility"
            subtitle="Reading comfort, notifications, and privacy."
          />

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <section className="lexi-card p-5" aria-label="Reading preferences">
              <p className="lexi-eyebrow">Reading preferences</p>
              <div className="mt-4 flex min-h-[44px] items-center justify-between gap-4 font-body-md text-on-surface">
                <span>Plain English by default</span>
                <Switch checked={plainDefault} onChange={setPlainDefault} label="Plain English by default" />
              </div>
              <div className="mt-4">
                <p id="font-label" className="font-label-md text-on-surface">Text size</p>
                <div className="mt-2">
                  <SegmentedControl
                    options={TEXT_SIZES}
                    value={fontSize}
                    onChange={setFontSize}
                    label="Text size"
                  />
                </div>
              </div>
              <div className="mt-4 flex min-h-[44px] items-center justify-between gap-4 font-body-md text-on-surface">
                <span>Reduce motion</span>
                <Switch checked={motion} onChange={setMotion} label="Reduce motion" />
              </div>
            </section>

            <section className="lexi-card p-5" aria-label="Account">
              <p className="lexi-eyebrow">Account & privacy</p>
              <ul className="mt-3 space-y-2 font-body-md text-on-surface-variant">
                <li>• ada@example.com — Pro workspace</li>
                <li>• Zero-retention processing enabled</li>
                <li>• Documents auto-delete after 30 days</li>
              </ul>
              <button type="button" className="lexi-btn-secondary mt-4 w-full">Download my data</button>
              <button type="button" className="mt-2 min-h-[44px] w-full rounded-xl font-label-md text-error hover:bg-error-container/50">Delete account</button>
            </section>
          </div>
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
