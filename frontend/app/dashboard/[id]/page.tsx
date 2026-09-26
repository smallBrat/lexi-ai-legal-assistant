"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, FileText, Languages, LayoutList, RotateCcw, Send, Square } from "lucide-react";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { ChatErrorBoundary, DashboardErrorBoundary } from "@/components/shared/error-boundary";
import { GlossaryChip } from "@/components/shared/glossary-chip";
import { PageTransition } from "@/components/shared/page-transition";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { isAnalysisInFlight, abortChatForDocument, useAnalyzeDocument, useChat, useDocument, useSendChatMessage } from "@/hooks/use-lexi";
import { isValidDocumentId, parseDocumentId } from "@/lib/document-id";
import type { ChatMessage } from "@/types";

// Heavy sections are lazy-loaded so the initial dashboard bundle stays small.
const ClauseCard = dynamic(
  () => import("@/components/shared/clause-card").then((m) => ({ default: m.ClauseCard })),
  {
    loading: () => (
      <div className="space-y-3" aria-label="Loading clauses">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24" />
        <Skeleton className="h-16" />
      </div>
    ),
  }
);
const Timeline = dynamic(
  () => import("@/components/shared/timeline").then((m) => ({ default: m.Timeline })),
  { loading: () => <Skeleton className="h-24" /> }
);
const QuestionCard = dynamic(
  () => import("@/components/shared/question-card").then((m) => ({ default: m.QuestionCard })),
  { loading: () => <Skeleton className="h-16" /> }
);

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutList },
  { id: "clauses", label: "Clause Explorer", icon: FileText },
  { id: "plain", label: "Plain English", icon: Languages },
  { id: "chat", label: "AI Chat", icon: Bot },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function DocumentDetailPage(): React.JSX.Element {
  const params = useParams();
  const id = parseDocumentId(params.id as string | string[] | undefined);
  const idValid = isValidDocumentId(id);
  const [tab, setTab] = useState<TabId>("overview");

  // Canonical source of truth: GET /documents/:id (includes analysis).
  // No separate useAnalysis query here — that POST endpoint is triggered
  // exactly once via the analyze mutation below, then the document query
  // is invalidated/refetched so this page updates without a manual refresh.
  const documentQuery = useDocument(id);
  const document = documentQuery.data;
  const analysis = document?.analysis;
  const isCompleted = document?.status === "ready";
  const analyze = useAnalyzeDocument();
  const analyzeTriggered = useRef(false);

  // Chat history loads only when the user opens the AI Chat tab on a
  // completed document — never during processing, never on dashboard mount.
  const chatEnabled = tab === "chat" && isCompleted && analysis != null;
  const { data: history } = useChat(id, { enabled: chatEnabled });
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [draft, setDraft] = useState("");
  const sendChat = useSendChatMessage();
  const sending = sendChat.isPending;
  const [chatError, setChatError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const chatLogRef = useRef<HTMLDivElement>(null);

  const chat: ChatMessage[] = messages ?? history ?? [];

  // Trigger POST /analyze once when the document is ready but has no
  // analysis yet (e.g. user deep-linked to the dashboard, or the
  // processing page was skipped). Never auto-fires for analysis_failed
  // (that needs an explicit user Retry) or while another analyze request
  // for this document is already running. Guarded so it never fires twice.
  // Non-UUID ids never reach the network: POST /analyze/<non-uuid> fails
  // FastAPI path validation with 422 before the handler runs.
  useEffect(() => {
    if (!id || !isValidDocumentId(id) || !document || document.status !== "ready" || analysis != null) return;
    if (analyzeTriggered.current || analyze.isPending || isAnalysisInFlight(id)) return;
    analyzeTriggered.current = true;
    analyze.mutate({ documentId: id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, document?.status, analysis != null]);

  // Manual retry: bypasses nothing but the auto-fire guard is already set,
  // so this is the single active mutation for the document. Any previous
  // in-flight request is aborted by the mutation itself.
  function retryAnalysis(): void {
    if (!id || !isValidDocumentId(id) || analyze.isPending) return;
    analyzeTriggered.current = true;
    analyze.reset();
    analyze.mutate({ documentId: id });
  }

  // Reset the once-guard when navigating between documents.
  useEffect(() => {
    analyzeTriggered.current = false;
    setMessages(null);
    setChatError(null);
    setFailedQuestion(null);
  }, [id]);
  useEffect(() => {
    return () => {
      if (id && isValidDocumentId(id)) abortChatForDocument(id);
    };
  }, [id]);

  useEffect(() => {
    chatLogRef.current?.scrollTo({ top: chatLogRef.current.scrollHeight });
  }, [chat.length, sending, chatError]);

  function onTabKey(e: React.KeyboardEvent, index: number): void {
    let next: number | null = null;
    if (e.key === "ArrowRight") next = (index + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next !== null) {
      e.preventDefault();
      setTab(TABS[next].id);
      tabRefs.current[next]?.focus();
    }
  }

  // `userMsg` must already be in the log (appended optimistically by the
  // caller). On success only the answer is appended; on failure the error
  // banner + Retry appear and the typed message is restored to the input.
  async function sendQuestion(question: string): Promise<void> {
    setChatError(null);
    try {
      const answer = await sendChat.mutateAsync({ documentId: id, question });
      // Functional update: `chat` from the render closure may be stale if
      // history arrived mid-flight; appending avoids clobbering it.
      setMessages((prev) => {
        const base = prev ?? history ?? [];
        if (base.some((m) => m.id === answer.id)) return base;
        return [...base, answer];
      });
      setFailedQuestion(null);
    } catch (error) {
      // User-cancelled (Stop button / navigation): stay silent, keep the
      // typed message so nothing is lost.
      if (error instanceof DOMException && error.name === "AbortError") {
        setDraft(question);
        return;
      }
      const message = error instanceof Error ? error.message : "The chat request failed.";
      setChatError(message);
      setFailedQuestion(question);
      // Keep the typed message in the input on failure.
      setDraft(question);
    }
  }

  async function ask(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    const q = draft.trim();
    if (!q) return;
    // Defensive: the Send button is disabled while pending, but if a send
    // somehow fires mid-flight (e.g. programmatic submit), the mutation
    // aborts ONLY the previous message for this same document before
    // starting a fresh request with a new controller.
    if (sending) return;
    setDraft("");
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: q };
    setMessages((prev) => [...(prev ?? history ?? []), userMsg]);
    await sendQuestion(q);
  }

  async function retryChat(): Promise<void> {
    if (!failedQuestion || sending) return;
    // The failed user message is already in the log — resend without
    // duplicating it.
    await sendQuestion(failedQuestion);
  }

  function cancelChat(): void {
    if (id && isValidDocumentId(id)) abortChatForDocument(id);
  }

  const isLoadingDocument = documentQuery.isPending;
  const isProcessing = !isLoadingDocument && (document == null || analysis == null);
  // Retryable overload failure: backend persisted analysis_failed, or the
  // analyze mutation itself just errored (e.g. HTTP 503 MODEL_UNAVAILABLE).
  // Hidden while a retry is pending so a superseded (aborted) request never
  // flashes a failure card.
  const isOverloaded =
    !analyze.isPending &&
    (document?.status === "analysis_failed" || analyze.isError) &&
    analysis == null;
  const analysisFailed = document?.status === "failed" || documentQuery.isError;

  return (
    <DashboardErrorBoundary>
    <DashboardShell>
      <PageTransition>
        <main id="main">
          <Breadcrumbs
            trail={[{ label: "Dashboard", href: "/dashboard" }, { label: isLoadingDocument ? "Loading…" : analysis?.document_type ?? document?.title ?? "Document" }]}
          />
          {!idValid ? (
            <div className="space-y-4" role="alert">
              <p className="font-headline-sm text-on-surface">This document link looks invalid.</p>
              <p className="font-body-md text-on-surface-variant">
                Expected a document ID (UUID) but received {JSON.stringify(id || "(empty)")}.{" "}
                No request was sent. Please return to the dashboard and open a document from the list.
              </p>
              <Link href="/dashboard" className="lexi-btn-secondary inline-flex">Back to dashboard</Link>
            </div>
          ) : isLoadingDocument ? (
            <div className="space-y-4" aria-busy="true" aria-label="Uploading document">
              <p className="lexi-eyebrow" role="status">Uploading…</p>
              <Skeleton className="h-10 w-2/3" />
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
            </div>
          ) : analysisFailed && analysis == null ? (
            <div className="space-y-4" role="alert">
              <p className="font-headline-sm text-on-surface">Analysis failed for this document.</p>
              <p className="font-body-md text-on-surface-variant">
                {documentQuery.isError ? "The document could not be loaded." : "The analysis could not be completed."}{" "}
                Please return to the dashboard and try again.
              </p>
              <Link href="/dashboard" className="lexi-btn-secondary inline-flex">Back to dashboard</Link>
            </div>
          ) : isOverloaded ? (
            <div className="space-y-4">
              <div>
                <p className="lexi-code">{document?.title} • {document?.pages} pages</p>
                <h1 className="mt-1 font-headline-lg text-headline-lg text-on-surface">{document?.title}</h1>
              </div>
              <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface-container-low p-1" aria-label="Document views">
                {TABS.map((t) => {
                  const Icon = t.icon;
                  return (
                    <button
                      key={t.id}
                      disabled
                      aria-disabled="true"
                      className="flex min-h-[44px] flex-1 cursor-not-allowed items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 font-label-md text-on-surface-variant opacity-50"
                    >
                      <Icon size={16} aria-hidden /> {t.label}
                    </button>
                  );
                })}
              </div>
              <section className="lexi-card p-6 text-center" role="alert" aria-label="Analysis unavailable">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-error/10 text-error">
                  <AlertTriangle size={24} aria-hidden />
                </span>
                <h2 className="mt-3 font-headline-sm text-headline-sm text-on-surface">Analysis unavailable</h2>
                <p className="mx-auto mt-2 max-w-md font-body-md text-on-surface-variant">
                  AI analysis couldn&apos;t be completed because Gemini free models are currently busy.
                </p>
                <Button onClick={retryAnalysis} disabled={analyze.isPending} className="mt-4 min-h-[44px]">
                  <RotateCcw size={18} aria-hidden />
                  {analyze.isPending ? "Retrying…" : "Retry Analysis"}
                </Button>
                <p className="mt-2 font-label-md text-on-surface-variant">
                  Your uploaded document is safe — nothing was lost.
                </p>
              </section>
            </div>
          ) : isProcessing || analysis == null ? (
            <div className="space-y-4" aria-busy="true" aria-label="Processing analysis">
              <p className="lexi-eyebrow" role="status">Processing analysis…</p>
              <Skeleton className="h-10 w-2/3" />
              <div className="grid gap-4 lg:grid-cols-3" aria-label="Loading overview">
                <div className="space-y-3 rounded-2xl border border-outline-variant/40 p-5 lg:col-span-2">
                  <Skeleton className="h-5 w-1/4" />
                  <Skeleton className="h-24" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
                <div className="space-y-3 rounded-2xl border border-outline-variant/40 p-5">
                  <Skeleton className="h-5 w-1/2" />
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                </div>
                <div className="space-y-3 rounded-2xl border border-outline-variant/40 p-5 lg:col-span-2">
                  <Skeleton className="h-5 w-1/4" />
                  <Skeleton className="h-20" />
                </div>
                <div className="space-y-3 rounded-2xl border border-outline-variant/40 p-5">
                  <Skeleton className="h-5 w-1/2" />
                  <Skeleton className="h-16" />
                </div>
              </div>
              <div className="grid gap-4" aria-label="Loading clauses">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="space-y-3 rounded-2xl border border-outline-variant/40 p-5">
                    <Skeleton className="h-5 w-1/3" />
                    <Skeleton className="h-20" />
                    <Skeleton className="h-12" />
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="lexi-code">{document?.title} • {document?.pages} pages</p>
                  <h1 className="mt-1 font-headline-lg text-headline-lg text-on-surface">{analysis.document_type}</h1>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {analysis.risk_level ? <RiskBadge level={analysis.risk_level} /> : null}
                    <Badge tone="neutral">Score {analysis.risk_score}/100</Badge>
                    <Badge tone="neutral">Reading level {analysis.reading_difficulty}/20</Badge>
                  </div>
                </div>
                <Link href="/report" className="lexi-btn-secondary">Export report</Link>
              </div>

              <div className="mt-6 flex gap-1 overflow-x-auto rounded-xl bg-surface-container-low p-1" role="tablist" aria-label="Document views">
                {TABS.map((t, index) => {
                  const Icon = t.icon;
                  const active = tab === t.id;
                  return (
                    <button
                      key={t.id}
                      ref={(el) => {
                        tabRefs.current[index] = el;
                      }}
                      role="tab"
                      id={`tab-${t.id}`}
                      aria-selected={active}
                      aria-controls={`panel-${t.id}`}
                      tabIndex={active ? 0 : -1}
                      onClick={() => setTab(t.id)}
                      onKeyDown={(e) => onTabKey(e, index)}
                      className={cn(
                        "flex min-h-[44px] flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 font-label-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                        active ? "bg-surface-container-lowest text-on-surface shadow-card font-semibold" : "text-on-surface-variant hover:text-on-surface"
                      )}
                    >
                      <Icon size={16} aria-hidden /> {t.label}
                    </button>
                  );
                })}
              </div>

              {tab === "overview" ? (
                <div className="mt-6 grid gap-4 lg:grid-cols-3" role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
                  <section className="lexi-card p-5 lg:col-span-2" aria-label="Summary">
                    <p className="lexi-eyebrow">Executive summary</p>
                    <p className="mt-2 font-body-md text-on-surface leading-relaxed">{analysis.summary}</p>
                    <p className="lexi-eyebrow mt-5">Risk score</p>
                    <Progress value={analysis.risk_score} className="mt-2" />
                    <ul className="mt-3 space-y-1.5">
                      {analysis.risk_reasons.map((r, i) => (
                        <li key={`${i}-${r}`} className="font-body-md text-on-surface-variant">• {r}</li>
                      ))}
                    </ul>
                  </section>
                  <section className="lexi-card p-5" aria-label="Obligations">
                    <p className="lexi-eyebrow">Your obligations</p>
                    <ul className="mt-3 space-y-3">
                      {analysis.obligations.map((o, i) => (
                        <li key={`${i}-${o.who}-${o.action}`} className="rounded-lg bg-surface-container-low p-3">
                          <p className="font-label-md font-semibold text-on-surface">{o.action}</p>
                          <p className="lexi-code mt-1">{o.who} • {o.deadline} • {o.priority}</p>
                        </li>
                      ))}
                    </ul>
                  </section>
                  <section className="lexi-card p-5 lg:col-span-2" aria-label="Timeline">
                    <p className="lexi-eyebrow">Key dates</p>
                    <div className="mt-4"><Timeline items={analysis.timeline} /></div>
                  </section>
                  <section className="lexi-card p-5" aria-label="Lawyer questions">
                    <p className="lexi-eyebrow">Ask your lawyer</p>
                    <ul className="mt-3 space-y-3">
                      {analysis.questions_for_lawyer.slice(0, 3).map((q, i) => (
                        <QuestionCard key={`${i}-${q}`} question={q} index={i} />
                      ))}
                    </ul>
                    <Link href="/report" className="mt-3 inline-flex min-h-[44px] items-center font-label-md text-primary hover:underline">
                      Open the full preparation pack →
                    </Link>
                  </section>
                </div>
              ) : null}

              {tab === "clauses" ? (
                <div className="mt-6 grid gap-4" role="tabpanel" id="panel-clauses" aria-labelledby="tab-clauses" aria-label="Clause explorer">
                  {analysis.clauses.map((c, i) => (
                    <ClauseCard key={`${i}-${c.title}`} clause={c} />
                  ))}
                  {analysis.clauses.length === 0 && (
                    <p className="lexi-eyebrow text-center py-8">No clauses found in this document.</p>
                  )}
                </div>
              ) : null}

              {tab === "plain" ? (
                <div className="mt-6 space-y-4" role="tabpanel" id="panel-plain" aria-labelledby="tab-plain" aria-label="Plain English view">
                  <section className="lexi-card p-6">
                    <p className="lexi-eyebrow">In plain English</p>
                    <p className="mt-2 font-body-lg text-body-lg text-on-surface leading-relaxed">{analysis.plain_english_summary}</p>
                  </section>
                    <section className="grid gap-3 md:grid-cols-2" aria-label="Glossary">
                      {analysis.glossary.map((g, i) => (
                        <GlossaryChip key={`${i}-${g.term}`} item={g} />
                      ))}
                  </section>
                </div>
              ) : null}

              {tab === "chat" ? (
                <ChatErrorBoundary>
                <section
                  className="mt-6 lexi-card flex min-h-[480px] flex-col p-0 overflow-hidden"
                  role="tabpanel"
                  id="panel-chat"
                  aria-labelledby="tab-chat"
                  aria-label="AI chat with document"
                >
                  <div ref={chatLogRef} className="flex-1 space-y-4 overflow-auto p-5 max-h-[60vh]">
                    {chat.map((m) => (
                      <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                        <div
                          className={cn(
                            "max-w-[85%] rounded-2xl p-4",
                            m.role === "user" ? "bg-primary text-on-primary" : "bg-surface-container-low text-on-surface"
                          )}
                        >
                          <p className="font-body-md">{m.content}</p>
                          {m.citations?.map((c, index) => (
                            <p key={`${c.clauseTitle}-${c.section}-${index}`} className="mt-2 rounded-lg bg-surface-container-lowest/70 p-2 font-label-sm text-on-surface-variant">
                              <strong>{c.clauseTitle}</strong> • {c.section} — “{c.excerpt}”
                            </p>
                          ))}
                        </div>
                      </div>
                    ))}
                    {sending ? (
                      <p className="font-label-md text-on-surface-variant" role="status" aria-live="polite">
                        <span className="inline-flex items-center gap-2">
                          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" aria-hidden />
                          Lexi is reading your document…
                        </span>
                      </p>
                    ) : null}
                    {chatError ? (
                      <div className="rounded-2xl border border-error/30 bg-error/5 p-4" role="alert" aria-live="assertive">
                        <p className="font-label-md font-semibold text-error">Message failed to send</p>
                        <p className="mt-1 font-body-md text-on-surface-variant">{chatError}</p>
                        <Button onClick={() => void retryChat()} disabled={sending} className="mt-3 min-h-[44px]" variant="secondary">
                          <RotateCcw size={16} aria-hidden />
                          Retry
                        </Button>
                      </div>
                    ) : null}
                  </div>
                  <form onSubmit={(e) => void ask(e)} className="flex gap-2 border-t border-outline-variant/40 p-4">
                    <label htmlFor="chat-input" className="sr-only">Ask about this document</label>
                    <Input id="chat-input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask about termination, payments, IP…" />
                    {sending ? (
                      <Button type="button" size="icon" className="shrink-0" aria-label="Stop generating" onClick={cancelChat} variant="secondary">
                        <Square size={18} aria-hidden />
                      </Button>
                    ) : null}
                    <Button type="submit" size="icon" className="shrink-0" aria-label="Send message" disabled={sending || !draft.trim()}>
                      <Send size={18} aria-hidden />
                    </Button>
                  </form>
                </section>
                </ChatErrorBoundary>
              ) : null}
            </>
          )}
        </main>
      </PageTransition>
    </DashboardShell>
    </DashboardErrorBoundary>
  );
}
