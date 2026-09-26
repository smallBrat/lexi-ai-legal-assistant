import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAnalysis } from "@/services/analysis";
import { isValidDocumentId } from "@/lib/document-id";
import { getChatHistory, sendChatMessage } from "@/services/chat";
import type { ChatMessage } from "@/types";
import { compareDocuments } from "@/services/compare";
import { listDocuments, getDocument, deleteDocument, type ListDocumentsParams } from "@/services/documents";
import { listRights } from "@/services/rights";
import { uploadDocument } from "@/services/upload";
import { pollingRegistry } from "@/lib/polling-registry";
import { usePolling } from "@/hooks/use-polling";
import type { LegalAnalysis, PaginatedDocumentsResponse, UploadResponse } from "@/types";

export function useDocuments(params: ListDocumentsParams = {}) {
  const query = useQuery<PaginatedDocumentsResponse>({
    queryKey: ["documents", params],
    queryFn: () => listDocuments(params),
    retry: 1,
  });
  const documents = query.data?.items ?? [];
  return {
    ...query,
    data: documents,
    documents,
    items: documents,
    page: query.data?.page ?? params.page ?? 1,
    totalPages: query.data?.total_pages ?? 0,
    totalItems: query.data?.total_items ?? 0,
    hasNext: query.data?.has_next ?? false,
    hasPrevious: query.data?.has_previous ?? false,
  };
}

export function useDocument(documentId: string) {
  // GET only. Never enabled for a non-UUID id: the query stays idle and no
  // request (not even a client-side 422) is produced — callers render an
  // invalid-ID error state instead.
  const valid = isValidDocumentId(documentId);

  // Persistent polling via registry — survives route transitions.
  // Phase 14.1: the polling hook is the ONLY network source for this
  // document; it pushes every result into the React Query cache via
  // queryClient.setQueryData(["document", id], result).
  const { document: pollingDocument, isPolling, error: pollingError } = usePolling({
    documentId: valid ? documentId : "",
  });  const query = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => {
      // Phase 14.2: this queryFn runs ONLY when the registry is not polling
      // this document (see `enabled` below) AND the poll loop has not
      // already seeded the cache — i.e. a one-shot fill for an already-
      // terminal document (deep-link to /dashboard/{id} after analysis
      // finished). While polling owns the document, every result arrives
      // via queryClient.setQueryData and this never executes.
       
      console.info("[lexi][polling] QUERY_FETCH", {
        at: new Date().toISOString(),
        documentId,
      });
      return getDocument(documentId);
    },
    // Phase 14.2: THREE independent guards keep React Query from ever
    // issuing a GET while polling owns the document:
    //   1. !isPolling        — the live hook state from usePolling
    //   2. peekStatus check  — registry truth, survives re-renders
    //   3. !pollingDocument  — no poll result has been pushed yet
    // refetchOnMount/refetchOnWindowFocus stay false permanently, so a
    // mount of dashboard/compare/report can never duplicate a fetch.
    enabled:
      Boolean(documentId) &&
      valid &&
      !isPolling &&
      pollingRegistry.peekStatus(documentId) !== "polling" &&
      pollingDocument == null,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    retry: 1,
    initialData: pollingDocument ?? undefined,
  });

  return { ...query, isPolling, pollingError };
}

export function useAnalysis(documentId: string, options?: { enabled?: boolean }) {
  // GET only — never POST. Reads the cached document (`GET /documents/:id`)
  // and derives `document.analysis` from it, so Report/Compare consumers can
  // never trigger analysis as a side effect. The ONLY writer is the
  // `useAnalyzeDocument` mutation, fired exactly once by the processing page
  // (or by an explicit user Retry on the dashboard).
  const valid = isValidDocumentId(documentId);
  return useQuery<LegalAnalysis | null>({
    queryKey: ["analysis", documentId],
    queryFn: async () => {
      const document = await getDocument(documentId);
      return document.analysis ?? null;
    },
    enabled: Boolean(documentId) && valid && (options?.enabled ?? true),
    retry: 1,
    refetchInterval: false,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

// Module-level registry guaranteeing a single active analysis request per
// document across hook instances. A new mutate() aborts the previous
// in-flight request for the same document (e.g. double-pressed Retry).
const activeAnalyzeControllers = new Map<string, AbortController>();

export function isAnalysisInFlight(documentId: string): boolean {
  return activeAnalyzeControllers.has(documentId);
}

export function useAnalyzeDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ documentId, force = false }: { documentId: string; force?: boolean }) => {
      // Belt-and-braces with the service-level guard: never emit
      // POST /analyze/:id for a non-UUID id (processing-page fallback,
      // dashboard deep-link, or retry button with a bad id).
      if (!isValidDocumentId(documentId)) {
        throw new Error(`Invalid document ID: expected a UUID, received ${JSON.stringify(documentId)}.`);
      }
      activeAnalyzeControllers.get(documentId)?.abort();
      const controller = new AbortController();
      activeAnalyzeControllers.set(documentId, controller);
      try {
        return await getAnalysis(documentId, force, controller.signal);
      } finally {
        if (activeAnalyzeControllers.get(documentId) === controller) {
          activeAnalyzeControllers.delete(documentId);
        }
      }
    },
    onSuccess: (analysis, variables) => {
      // Phase 14.2 req. 5: NEVER invalidateQueries for a document the poll
      // loop owns — invalidation triggers a refetch that would duplicate
      // the poll. Push the analysis into the cached document instead; if
      // no cache entry exists yet (poll hasn't delivered one), set it so
      // consumers render immediately without a GET.
      const cached = queryClient.getQueryData<unknown>(["document", variables.documentId]) as
        | { analysis?: unknown }
        | undefined;
      if (cached) {
        queryClient.setQueryData(["document", variables.documentId], { ...cached, analysis });
      } else {
        queryClient.setQueryData(["document", variables.documentId], { analysis });
      }
      queryClient.setQueryData(["analysis", variables.documentId], analysis);
      // Dashboard list is a different endpoint (GET /documents) — safe to
      // invalidate; it is not owned by the per-document poll loop.
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation<UploadResponse, Error, { file: File; documentType: string; title?: string; onProgress?: (progress: number) => void }>({
    mutationFn: ({ file, documentType, title, onProgress }) => uploadDocument(file, documentType, title, onProgress),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["documents"] }); },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: deleteDocument, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["documents"] }); } });
}

export function useChat(documentId: string, options?: { enabled?: boolean }) {
  // History GET only, and only when the caller explicitly opts in (dashboard
  // chat tab on a completed document). Never enabled for non-UUID ids;
  // POSTs happen solely via `sendChatMessage` on user submit.
  const valid = isValidDocumentId(documentId);
  return useQuery({
    queryKey: ["chat", documentId],
    queryFn: () => getChatHistory(documentId),
    enabled: Boolean(documentId) && valid && (options?.enabled ?? false),
    retry: 1,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

// Module-level registry guaranteeing a single active chat request per
// document across hook instances — fully independent from the analyze
// registry above, so an analyze mutation can never abort a chat (and
// vice versa). A new send aborts the previous in-flight chat for the SAME
// document only (user sent another message while one was pending).
// Each message gets a FRESH AbortController; an aborted controller is never
// reused because it is deleted from the map in the mutation's finally block.
const activeChatControllers = new Map<string, AbortController>();

export function isChatInFlight(documentId: string): boolean {
  return activeChatControllers.has(documentId);
}

/** Abort the pending chat request for one document (navigation/unmount/Stop). */
export function abortChatForDocument(documentId: string): void {
  activeChatControllers.get(documentId)?.abort();
  activeChatControllers.delete(documentId);
}

export function useSendChatMessage() {
  const queryClient = useQueryClient();
  return useMutation<ChatMessage, Error, { documentId: string; question: string }>({
    mutationFn: async ({ documentId, question }) => {
      if (!isValidDocumentId(documentId)) {
        throw new Error(`Invalid document ID: expected a UUID, received ${JSON.stringify(documentId)}.`);
      }
      // Cancel ONLY the previous pending message for this same document.
      activeChatControllers.get(documentId)?.abort();
      const controller = new AbortController();
      activeChatControllers.set(documentId, controller);
      try {
        return await sendChatMessage(documentId, question, controller.signal);
      } finally {
        if (activeChatControllers.get(documentId) === controller) {
          activeChatControllers.delete(documentId);
        }
      }
    },
    onSuccess: (_answer, variables) => {
      // Refresh server history so the new exchange appears even after a
      // remount; the page also appends the answer locally for instant UX.
      void queryClient.invalidateQueries({ queryKey: ["chat", variables.documentId] });
    },
  });
}

export function useComparison(aId: string, bId: string, options?: { enabled?: boolean }) {
  // Idle until BOTH ids are valid UUIDs explicitly supplied by the caller
  // (?a=&b=). No polling, no auto-fire — compare never starts analysis.
  const ready = Boolean(aId && bId) && isValidDocumentId(aId) && isValidDocumentId(bId) && (options?.enabled ?? true);
  return useQuery({
    queryKey: ["compare", aId, bId],
    queryFn: () => compareDocuments(aId, bId),
    enabled: ready,
    retry: 1,
    refetchInterval: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useRights() {
  return useQuery({ queryKey: ["rights"], queryFn: listRights });
}
