import { apiClient } from "@/lib/api-client";
import { CHAT_HISTORY_TIMEOUT_MS, CHAT_REQUEST_TIMEOUT_MS } from "@/lib/request-timeouts";
import { assertValidDocumentId } from "@/lib/document-id";
import type { ChatCitation, ChatMessage } from "@/types";

type BackendCitation = {
  clause_title: string;
  excerpt: string;
  page_number?: number | null;
  similarity_score: number;
};

type BackendChatMessage = {
  document_id: string;
  user_id: string;
  question: string;
  answer: string;
  citations: BackendCitation[];
  confidence_score: number;
  timestamp: string;
};

function mapCitation(citation: BackendCitation): ChatCitation {
  return {
    clauseTitle: citation.clause_title,
    section: citation.page_number === null || citation.page_number === undefined ? "Document" : `Page ${citation.page_number}`,
    excerpt: citation.excerpt,
  };
}

// Drop duplicate citations pointing at the same clause/page excerpt.
// Gemini (and the summary fallback) can return the same clause twice:
// e.g. several citations with `page_number: null` all render as
// "Document". Rendering duplicates confuses users and, worse, produces
// duplicate React keys downstream. Keep the first occurrence.
function dedupeCitations(citations: BackendCitation[]): BackendCitation[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const fingerprint = `${citation.clause_title}|||${citation.excerpt}|||${citation.page_number ?? ""}`;
    if (seen.has(fingerprint)) return false;
    seen.add(fingerprint);
    return true;
  });
}

function mapHistoryRow(message: BackendChatMessage): ChatMessage[] {
  // One stored exchange = the user's question + Lexi's answer. The old
  // mapper dropped `question`, so reopened history showed answers with no
  // questions. Expand each row into the pair the user actually saw.
  const base = `${message.document_id}-${message.timestamp}`;
  return [
    { id: `${base}-q`, role: "user", content: message.question },
    {
      id: `${base}-a`,
      role: "assistant",
      content: message.answer,
      citations: dedupeCitations(message.citations).map(mapCitation),
    },
  ];
}

export async function getChatHistory(documentId: string, signal?: AbortSignal): Promise<ChatMessage[]> {
  assertValidDocumentId(documentId);
  const response = await apiClient.get<BackendChatMessage[]>(
    `/documents/${encodeURIComponent(documentId)}/chat`,
    { timeoutMs: CHAT_HISTORY_TIMEOUT_MS, signal },
  );
  return response.flatMap(mapHistoryRow);
}

export async function sendChatMessage(
  documentId: string,
  question: string,
  signal?: AbortSignal,
): Promise<ChatMessage> {
  // Contract mirrors backend `ChatQuestionRequest` (min_length=1): fail fast
  // client-side instead of emitting a doomed POST that returns 422.
  assertValidDocumentId(documentId);
  const trimmed = question.trim();
  if (!trimmed) {
    throw new Error("Question cannot be empty.");
  }
  // Exact backend contract: POST /documents/{uuid}/chat with a JSON
  // `{ question }` body (ChatQuestionRequest, extra="forbid" — no extra
  // keys), Content-Type + Authorization attached by api-client.
  const response = await apiClient.post<{ answer: string; citations: BackendCitation[] }>(
    `/documents/${encodeURIComponent(documentId)}/chat`,
    { question: trimmed },
    { timeoutMs: CHAT_REQUEST_TIMEOUT_MS, signal },
  );
  return { id: `m-${Date.now()}`, role: "assistant", content: response.answer, citations: dedupeCitations(response.citations).map(mapCitation) };
}
