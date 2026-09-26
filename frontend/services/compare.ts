import { apiClient } from "@/lib/api-client";
import { assertValidDocumentId } from "@/lib/document-id";
import type { ComparisonHistoryItem, ComparisonResult } from "@/types";

export async function compareDocuments(aId: string, bId: string): Promise<ComparisonResult> {
  // Fail fast: never emit POST /compare for non-UUID ids (stray demo slugs).
  assertValidDocumentId(aId);
  assertValidDocumentId(bId);
  if (aId === bId) {
    throw new Error("Select two different documents to compare.");
  }
  return apiClient.post<ComparisonResult>("/compare", { document_a_id: aId, document_b_id: bId });
}

export async function listComparisons(limit = 20): Promise<ComparisonHistoryItem[]> {
  return apiClient.get<ComparisonHistoryItem[]>(`/compare?limit=${limit}`);
}
