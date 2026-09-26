import { apiClient, pollingFetch } from "@/lib/api-client";
import { DOCUMENT_FETCH_TIMEOUT_MS } from "@/lib/request-timeouts";
import { assertValidDocumentId } from "@/lib/document-id";
import type { LegalAnalysis, LexiDocument, PaginatedDocumentsResponse, RiskLevel } from "@/types";

export interface ListDocumentsParams {
  page?: number;
  pageSize?: number;
  search?: string;
  documentType?: string;
  riskLevel?: RiskLevel;
  status?: "processing" | "completed" | "failed";
  sort?: "created_at" | "risk_score" | "title";
  order?: "asc" | "desc";
}

type BackendDocument = {
  id: string;
  title: string;
  document_type: string;
  status: "processing" | "completed" | "failed" | "analysis_failed";
  storage_path?: string;
  pages?: number;
  created_at?: string;
  risk_score?: number;
  risk_level?: string;
  flag_count?: number;
  analysis?: LegalAnalysis | null;
};

function mapDocument(document: BackendDocument): LexiDocument {
  const analysis = document.analysis;
  const riskScore = document.risk_score ?? analysis?.risk_score ?? 0;
  const riskLevel = (document.risk_level ?? analysis?.risk_level ?? "low") as RiskLevel;
  const flags = document.flag_count ?? analysis?.clauses.length ?? 0;
  return {
    id: document.id,
    title: document.title,
    fileName: document.storage_path ?? document.title,
    documentType: document.document_type,
    pages: document.pages ?? 0,
    sizeKb: 0,
    uploadedAt: document.created_at ?? new Date().toISOString(),
    status: document.status === "completed" ? "ready" : document.status,
    riskScore,
    riskLevel,
    flags,
    analysis: analysis ?? undefined,
  };
}

export async function listDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocumentsResponse> {
  const query = new URLSearchParams();
  if (params.page !== undefined) query.set("page", String(params.page));
  if (params.pageSize !== undefined) query.set("page_size", String(params.pageSize));
  if (params.search?.trim()) query.set("search", params.search.trim());
  if (params.documentType) query.set("document_type", params.documentType);
  if (params.riskLevel) query.set("risk_level", params.riskLevel);
  if (params.status) query.set("status", params.status);
  if (params.sort) query.set("sort", params.sort);
  if (params.order) query.set("order", params.order);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await apiClient.get<{
    items: BackendDocument[];
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_previous: boolean;
  }>(`/documents${suffix}`);
  return { ...response, items: response.items.map(mapDocument) };
}

export async function getDocument(id: string): Promise<LexiDocument> {
  assertValidDocumentId(id);
  return mapDocument(
    await apiClient.get<BackendDocument>(`/documents/${encodeURIComponent(id)}`, {
      timeoutMs: DOCUMENT_FETCH_TIMEOUT_MS,
    }),
  );
}

/** Polling-optimized document fetch: always gets a fresh JWT session
 *  before each request, designed for long-running polling loops. */
export async function pollingGetDocument(id: string): Promise<LexiDocument> {
  assertValidDocumentId(id);
  return mapDocument(
    await pollingFetch<BackendDocument>(`/documents/${encodeURIComponent(id)}`, {}, {
      timeoutMs: DOCUMENT_FETCH_TIMEOUT_MS,
    }),
  );
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient.post<void>(`/documents/${encodeURIComponent(id)}/delete`);
}
