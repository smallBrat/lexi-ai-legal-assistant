"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  FileDiff,
  GitCompareArrows,
  MinusCircle,
  PlusCircle,
  RefreshCcw,
  Scale,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { PageTransition } from "@/components/shared/page-transition";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useComparison } from "@/hooks/use-lexi";
import { isValidDocumentId } from "@/lib/document-id";
import { ApiError } from "@/lib/api-client";
import type { CompareClause } from "@/types";
import { cn } from "@/lib/utils";

export default function ComparisonResultsPage(): React.JSX.Element {
  return (
    <Suspense>
      <ComparisonResultsInner />
    </Suspense>
  );
}

function similarityTone(score: number): "low" | "medium" | "high" {
  if (score >= 75) return "low";
  if (score >= 40) return "medium";
  return "high";
}

function clauseTone(similarity: CompareClause["similarity"]): "low" | "medium" | "high" | "info" {
  if (similarity === "identical" || similarity === "similar") return "low";
  if (similarity === "changed") return "medium";
  return "high";
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && "status" in error) {
    const status = (error as { status: number }).status;
    switch (status) {
      case 401:
        return "Authentication expired. Please refresh the page.";
      case 503:
        return "Backend busy — please wait and the comparison will proceed.";
      case 500:
      case 502:
      case 504:
        return "Temporary server error — will retry automatically.";
      default:
        return (error as Error).message ?? "Comparison failed.";
    }
  }
  if (error instanceof Error && error.message.includes("timeout")) {
    return "Request timed out — the backend is still processing. Please wait.";
  }
  if (error instanceof Error && error.message.includes("Network")) {
    return "Network connection lost — will retry when reconnected.";
  }
  return (error as Error)?.message ?? "Something went wrong.";
}

function isTransientError(error: unknown): boolean {
  if (error instanceof Error && "status" in error) {
    const status = (error as { status: number }).status;
    return status >= 500 || status === 0;
  }
  return false;
}

function ComparisonResultsInner(): React.JSX.Element {
  const params = useSearchParams();
  const aId = params.get("a") ?? "";
  const bId = params.get("b") ?? "";
  const idsPresent = Boolean(aId && bId);
  const idsValid = idsPresent && isValidDocumentId(aId) && isValidDocumentId(bId);
  const distinct = idsValid && aId !== bId;
  const ready = distinct;
  const { data, isLoading, isError, error, refetch, isFetching } = useComparison(ready ? aId : "", ready ? bId : "", {
    enabled: ready,
  });
  const [openClauses, setOpenClauses] = useState<Set<string>>(new Set());

  const toggleClause = (name: string) => {
    setOpenClauses((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const pendingDetail = (error as ApiError | null)?.details as
    | { document_a_ready?: boolean; document_b_ready?: boolean }
    | null
    | undefined;
  const isPending =
    isError &&
    (error as ApiError | null)?.status === 422 &&
    (pendingDetail?.document_a_ready === false || pendingDetail?.document_b_ready === false);

  const isTransient = isError && isTransientError(error);
  const errorMessage = isError ? getErrorMessage(error) : null;

  const metrics = data?.result.metrics;
  const clauses = data?.result.clauses ?? [];
  const summaryRows: Array<[string, string, string]> = data
    ? [
        ["Purpose", data.result.summary.purpose_a, data.result.summary.purpose_b],
        ["Parties", data.result.summary.parties_a, data.result.summary.parties_b],
        ["Agreement type", data.result.summary.agreement_type_a, data.result.summary.agreement_type_b],
        ["Effective dates", data.result.summary.effective_dates_a, data.result.summary.effective_dates_b],
        ["Expiry", data.result.summary.expiry_a, data.result.summary.expiry_b],
        ["Jurisdiction", data.result.summary.jurisdiction_a, data.result.summary.jurisdiction_b],
        ["Governing law", data.result.summary.governing_law_a, data.result.summary.governing_law_b],
      ]
    : [];

  return (
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs
            trail={[
              { label: "Dashboard", href: "/dashboard" },
              { label: "Compare", href: "/compare" },
              { label: "Results" },
            ]}
          />

          {!idsPresent ? (
            <>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Comparison Results</h1>
              <p className="mt-4 font-body-md text-on-surface-variant">
                Select two documents to compare — no comparison was requested.{" "}
                <Link href="/compare" className="text-primary underline">
                  Back to Compare
                </Link>
              </p>
            </>
          ) : !idsValid ? (
            <>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Comparison Results</h1>
              <p className="mt-4 font-body-md text-on-surface-variant" role="alert">
                Those document links look invalid — expected two document IDs (UUIDs). No request was sent.{" "}
                <Link href="/compare" className="text-primary underline">
                  Back to Compare
                </Link>
              </p>
            </>
          ) : !distinct ? (
            <>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Comparison Results</h1>
              <p className="mt-4 font-body-md text-on-surface-variant" role="alert">
                Both sides reference the same document — pick two different documents.{" "}
                <Link href="/compare" className="text-primary underline">
                  Back to Compare
                </Link>
              </p>
            </>
          ) : isLoading || (!data && !isError) ? (
            <div className="mt-6 space-y-4" aria-busy="true" aria-label="Loading comparison">
              <Skeleton className="h-32" />
              <Skeleton className="h-32" />
              <Skeleton className="h-32" />
            </div>
          ) : isError && !data ? (
            <>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Comparison Results</h1>
              <div className="lexi-card mt-6 p-5" role="alert">
                <p className="font-headline-sm text-headline-sm text-on-surface">
                  {isPending
                    ? "Analysis still running"
                    : isTransient
                      ? "Connection issue"
                      : "Comparison failed"}
                </p>
                <p className="mt-2 font-body-md text-on-surface-variant">
                  {isPending
                    ? `Document A ${pendingDetail?.document_a_ready ? "is ready" : "is still being analyzed"} • Document B ${
                        pendingDetail?.document_b_ready ? "is ready" : "is still being analyzed"
                      }. Wait for both analyses, then retry.`
                    : errorMessage ?? "Something went wrong."}
                </p>
                <div className="mt-4 flex gap-2">
                  {(isTransient || isPending) ? (
                    <button
                      type="button"
                      className="lexi-btn-primary"
                      onClick={() => refetch()}
                      disabled={isFetching}
                    >
                      <RefreshCcw size={16} aria-hidden /> {isFetching ? "Retrying…" : "Retry"}
                    </button>
                  ) : null}
                  <Link href="/compare" className="lexi-btn-secondary">
                    <ArrowLeft size={16} aria-hidden /> Back to Compare
                  </Link>
                </div>
              </div>
            </>
          ) : data ? (
            <>
              {/* Hero */}
              <div className="lexi-card mt-2 p-6">
                <p className="lexi-eyebrow flex items-center gap-2">
                  <FileDiff size={16} className="text-primary" aria-hidden /> Clause-by-clause comparison
                  {data.cached ? <Badge tone="info">cached</Badge> : null}
                </p>
                <h1 className="mt-2 font-headline-lg text-headline-lg text-on-surface">
                  {data.document_a_title || "Document A"} <span className="text-on-surface-variant">vs</span>{" "}
                  {data.document_b_title || "Document B"}
                </h1>
                <p className="lexi-code mt-1">
                  {data.document_a_id} vs {data.document_b_id}
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Badge tone={similarityTone(metrics?.similarity_score ?? 0)}>
                    {metrics?.similarity_score ?? 0}% similar
                  </Badge>
                  <span className="font-body-md text-on-surface-variant">
                    Generated {new Date(data.created_at).toLocaleString()}
                  </span>
                  <Link href="/compare" className="lexi-btn-ghost ml-auto">
                    <ArrowLeft size={16} aria-hidden /> New comparison
                  </Link>
                </div>
                <Progress value={metrics?.similarity_score ?? 0} className="mt-4" />
                {metrics?.similarity_justification ? (
                  <p className="mt-2 font-body-md text-on-surface-variant">{metrics.similarity_justification}</p>
                ) : null}
              </div>

              {/* Metric cards */}
              <div className="mt-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  { label: "Compared", value: String(metrics?.total_clauses_compared ?? clauses.length) },
                  { label: "Matched", value: String(metrics?.clauses_matched ?? 0) },
                  { label: "Changed", value: String(metrics?.clauses_changed ?? 0) },
                  { label: "Added in B", value: String(metrics?.clauses_added ?? 0) },
                  { label: "Removed from B", value: String(metrics?.clauses_removed ?? 0) },
                  { label: "Similarity", value: `${metrics?.similarity_score ?? 0}%` },
                ].map((s) => (
                  <div key={s.label} className="lexi-card p-4 text-center">
                    <p className="lexi-eyebrow">{s.label}</p>
                    <p className="font-headline-lg text-headline-lg text-on-surface">{s.value}</p>
                  </div>
                ))}
              </div>

              {/* Executive summary */}
              <section className="lexi-card mt-4 p-5" aria-label="Executive summary">
                <h2 className="flex items-center gap-2 font-headline-sm text-headline-sm text-on-surface">
                  <GitCompareArrows size={18} className="text-primary" aria-hidden /> Executive summary
                </h2>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left font-body-md">
                    <thead>
                      <tr className="lexi-code">
                        <th className="py-2 pr-4">Field</th>
                        <th className="py-2 pr-4">A — {data.document_a_title || "Document A"}</th>
                        <th className="py-2">B — {data.document_b_title || "Document B"}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summaryRows.map(([field, a, b]) => (
                        <tr key={field} className={cn("border-t border-outline-variant", a !== b && "bg-primary-fixed/20")}>
                          <td className="py-2 pr-4 font-semibold text-on-surface">{field}</td>
                          <td className="py-2 pr-4 text-on-surface">{a || "—"}</td>
                          <td className="py-2 text-on-surface">{b || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Clause comparison */}
              <section className="mt-4" aria-label="Clause comparison">
                <h2 className="font-headline-sm text-headline-sm text-on-surface">
                  Clause comparison ({clauses.length})
                </h2>
                <div className="mt-3 space-y-3">
                  {clauses.map((clause) => {
                    const open = openClauses.has(clause.clause_name);
                    return (
                      <article key={clause.clause_name} className="lexi-card p-5">
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 text-left"
                          onClick={() => toggleClause(clause.clause_name)}
                          aria-expanded={open}
                        >
                          {clause.similarity === "added" ? (
                            <PlusCircle size={18} className="shrink-0 text-tertiary" aria-hidden />
                          ) : clause.similarity === "removed" ? (
                            <MinusCircle size={18} className="shrink-0 text-error" aria-hidden />
                          ) : (
                            <RefreshCcw size={18} className="shrink-0 text-primary" aria-hidden />
                          )}
                          <span className="font-headline-sm text-headline-sm text-on-surface">
                            {clause.clause_name}
                          </span>
                          <Badge tone={clauseTone(clause.similarity)}>{clause.similarity}</Badge>
                          <span className="ml-auto font-label-md text-on-surface-variant">
                            {open ? "Hide" : "Show"}
                          </span>
                        </button>
                        {!clause.present_in_a || !clause.present_in_b ? (
                          <p className="mt-2 font-body-md text-on-surface-variant">
                            {!clause.present_in_a ? "Absent in A. " : ""}
                            {!clause.present_in_b ? "Absent in B." : ""}
                          </p>
                        ) : null}
                        {open ? (
                          <>
                            <div className="mt-3 grid gap-3 md:grid-cols-2">
                              <div className="rounded-lg bg-surface-container-low p-3">
                                <p className="lexi-code">A — Before</p>
                                <p className="mt-1 font-body-md text-on-surface">
                                  {clause.text_a || "—"}
                                </p>
                              </div>
                              <div className="rounded-lg bg-primary-fixed/30 p-3">
                                <p className="lexi-code">B — After</p>
                                <p className="mt-1 font-body-md text-on-surface">
                                  {clause.text_b || "—"}
                                </p>
                              </div>
                            </div>
                            {clause.difference_explanation ? (
                              <p className="mt-3 font-body-md text-on-surface">
                                <strong>Difference: </strong>
                                {clause.difference_explanation}
                              </p>
                            ) : null}
                            {clause.additional_obligations ? (
                              <p className="mt-1 font-body-md text-on-surface">
                                <strong>Additional obligations: </strong>
                                {clause.additional_obligations}
                              </p>
                            ) : null}
                          </>
                        ) : null}
                      </article>
                    );
                  })}
                  {clauses.length === 0 ? (
                    <p className="font-body-md text-on-surface-variant">No clauses were compared.</p>
                  ) : null}
                </div>
              </section>

              {/* Risk changes */}
              {data.result.risks.length > 0 ? (
                <section className="lexi-card mt-4 p-5" aria-label="Risk changes">
                  <h2 className="flex items-center gap-2 font-headline-sm text-headline-sm text-on-surface">
                    <ShieldAlert size={18} className="text-error" aria-hidden /> Risk changes
                  </h2>
                  <ul className="mt-3 space-y-2">
                    {data.result.risks.map((risk) => (
                      <li key={risk.risk} className="flex flex-wrap items-center gap-2 font-body-md text-on-surface">
                        <Badge tone={risk.severity}>{risk.severity}</Badge>
                        <Badge tone={risk.added ? "high" : risk.removed ? "low" : "neutral"}>
                          {risk.added ? "added" : risk.removed ? "removed" : "changed"}
                        </Badge>
                        <span className="font-semibold">{risk.risk}</span>
                        {risk.explanation ? (
                          <span className="w-full text-on-surface-variant">{risk.explanation}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {/* Rights added/removed */}
              {data.result.rights.length > 0 ? (
                <section className="mt-4" aria-label="Rights changes">
                  <h2 className="flex items-center gap-2 font-headline-sm text-headline-sm text-on-surface">
                    <Scale size={18} className="text-primary" aria-hidden /> Rights added / removed
                  </h2>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {data.result.rights.map((right) => (
                      <div key={right.role} className="lexi-card p-5">
                        <p className="font-label-md font-semibold text-on-surface">{right.role}</p>
                        {right.added.length > 0 ? (
                          <ul className="mt-2 space-y-1">
                            {right.added.map((item) => (
                              <li key={item} className="flex gap-2 font-body-md text-on-surface">
                                <PlusCircle size={16} className="mt-1 shrink-0 text-tertiary" aria-hidden />
                                {item}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {right.removed.length > 0 ? (
                          <ul className="mt-2 space-y-1">
                            {right.removed.map((item) => (
                              <li key={item} className="flex gap-2 font-body-md text-on-surface">
                                <MinusCircle size={16} className="mt-1 shrink-0 text-error" aria-hidden />
                                {item}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {right.added.length === 0 && right.removed.length === 0 ? (
                          <p className="mt-2 font-body-md text-on-surface-variant">No changes.</p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {/* Financial differences */}
              {data.result.financials.length > 0 ? (
                <section className="lexi-card mt-4 p-5" aria-label="Financial differences">
                  <h2 className="flex items-center gap-2 font-headline-sm text-headline-sm text-on-surface">
                    <Wallet size={18} className="text-primary" aria-hidden /> Financial differences
                  </h2>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-left font-body-md">
                      <thead>
                        <tr className="lexi-code">
                          <th className="py-2 pr-4">Term</th>
                          <th className="py-2 pr-4">A</th>
                          <th className="py-2 pr-4">B</th>
                          <th className="py-2">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.result.financials.map((row) => (
                          <tr key={row.term} className={cn("border-t border-outline-variant", row.changed && "bg-primary-fixed/20")}>
                            <td className="py-2 pr-4 font-semibold text-on-surface">{row.term}</td>
                            <td className="py-2 pr-4 text-on-surface">{row.value_a || "—"}</td>
                            <td className="py-2 pr-4 text-on-surface">{row.value_b || "—"}</td>
                            <td className="py-2">
                              <Badge tone={row.changed ? "medium" : "neutral"}>
                                {row.changed ? "changed" : "same"}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ) : null}

              {/* Timeline changes */}
              {data.result.timeline.length > 0 ? (
                <section className="lexi-card mt-4 p-5" aria-label="Timeline changes">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">Timeline changes</h2>
                  <ol className="mt-3 space-y-3 border-l-2 border-outline-variant pl-4">
                    {data.result.timeline.map((item) => (
                      <li key={item.event}>
                        <p className="font-label-md font-semibold text-on-surface">
                          {item.event}{" "}
                          {item.changed ? <Badge tone="medium">changed</Badge> : <Badge tone="neutral">same</Badge>}
                        </p>
                        <p className="font-body-md text-on-surface-variant">
                          A: {item.value_a || "—"} → B: {item.value_b || "—"}
                        </p>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              {/* Obligations */}
              {data.result.obligations.length > 0 ? (
                <section className="lexi-card mt-4 p-5" aria-label="Obligation comparison">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">Obligation comparison</h2>
                  <ul className="mt-3 space-y-2">
                    {data.result.obligations.map((ob) => (
                      <li key={ob.obligation} className="font-body-md text-on-surface">
                        <span className="font-semibold">{ob.obligation}</span>{" "}
                        {ob.changed ? <Badge tone="medium">changed</Badge> : null}
                        <span className="block text-on-surface-variant">
                          A ({ob.party_a || "—"}): {ob.detail_a || "—"} • B ({ob.party_b || "—"}):{" "}
                          {ob.detail_b || "—"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {/* Missing clauses */}
              {data.result.missing_clauses.length > 0 ? (
                <section className="lexi-card mt-4 p-5" aria-label="Missing clauses">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">Missing clauses</h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {data.result.missing_clauses.map((missing) => (
                      <span
                        key={`${missing.clause_name}-${missing.missing_from}`}
                        className="inline-flex items-center gap-1.5 rounded-full bg-surface-container px-3 py-1.5 font-label-md text-on-surface"
                        title={missing.excerpt || missing.clause_name}
                      >
                        <Badge tone={missing.missing_from === "A" ? "high" : "info"}>
                          {missing.missing_from === "A" ? "missing in A" : "missing in B"}
                        </Badge>
                        {missing.clause_name}
                      </span>
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          ) : null}
        </main>
      </PageTransition>
    </DashboardShell>
  );
}
