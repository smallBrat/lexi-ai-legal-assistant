import { apiClient } from "@/lib/api-client";
import {
  assertValidDocumentId,
  isValidDocumentId,
} from "@/lib/document-id";
import type { LegalAnalysis } from "@/types";

// Single source of truth lives in `@/lib/document-id`; re-exported here so
// existing imports (`@/services/analysis`) keep working.
export { assertValidDocumentId, isValidDocumentId };

export async function getAnalysis(
  documentId: string,
  force = false,
  signal?: AbortSignal,
): Promise<LegalAnalysis> {
  // Client-side contract guard: the backend path param is `document_id: UUID`,
  // so a non-UUID id (e.g. a hardcoded demo slug) can never succeed and would
  // surface as a 422 from FastAPI request validation before the handler runs.
  // Fail fast here instead of emitting another doomed POST /analyze/:id.
  assertValidDocumentId(documentId);
  const path = `/analyze/${encodeURIComponent(documentId)}${force ? "?force=true" : ""}`;
  return apiClient.post<LegalAnalysis>(
    path,
    undefined,
    { signal },
  );
}

export async function getPlainEnglish(documentId: string): Promise<{ summary: string; clauses: { title: string; simplified: string }[] }> {
  const analysis = await getAnalysis(documentId);
  return {
    summary: analysis.plain_english_summary,
    clauses: analysis.clauses.map((c) => ({ title: c.title, simplified: c.simplified_text })),
  };
}
