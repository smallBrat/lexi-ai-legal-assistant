import { apiClient } from "@/lib/api-client";

export interface ReportPayload {
  documentTitle: string;
  riskScore: number;
  clauses: number;
  questions: string[];
}

export async function buildReport(documentId: string): Promise<ReportPayload> {
  return apiClient.get<ReportPayload>(`/documents/${encodeURIComponent(documentId)}/report`);
}

export async function exportReport(documentId: string, format: "pdf" | "docx"): Promise<Blob> {
  return apiClient.get<Blob>(`/documents/${encodeURIComponent(documentId)}/report/export?format=${format}`);
}
