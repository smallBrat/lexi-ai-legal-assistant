import { FileUp, ShieldCheck } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageHeader } from "@/components/shared/page-header";
import { PageTransition } from "@/components/shared/page-transition";
import { UploadDropzone } from "@/components/shared/upload-dropzone";

export default function UploadPage(): React.JSX.Element {
  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs trail={[{ label: "Dashboard", href: "/dashboard" }, { label: "Upload Workspace" }]} />
          <PageHeader icon={FileUp} title="Upload Workspace" subtitle="Drop a contract in — Lexi handles the rest." />
          <div className="mt-6">
            <UploadDropzone />
          </div>
          <p className="mt-4 flex items-center gap-2 font-label-md text-on-surface-variant">
            <ShieldCheck size={16} className="text-tertiary" aria-hidden />
            Files are encrypted in transit and never retained for training.
          </p>
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
