/** Shared Lexi domain types — mirrors backend/app/schemas/analysis_schema.py */

export type RiskLevel = "low" | "medium" | "high";

export interface ClauseAnalysis {
  title: string;
  category: string;
  risk_level: RiskLevel;
  importance_score: number;
  original_text: string;
  simplified_text: string;
  why_it_matters: string;
}

export interface Obligation {
  who: string;
  action: string;
  deadline: string;
  priority: string;
}

export interface TimelineItem {
  date: string;
  event: string;
  description: string;
}

export interface GlossaryItem {
  term: string;
  definition: string;
}

export interface LegalAnalysis {
  summary: string;
  plain_english_summary: string;
  document_type: string;
  reading_difficulty: number;
  risk_score: number;
  risk_level?: RiskLevel | null;
  risk_reasons: string[];
  clauses: ClauseAnalysis[];
  obligations: Obligation[];
  timeline: TimelineItem[];
  glossary: GlossaryItem[];
  questions_for_lawyer: string[];
}

export interface LexiDocument {
  id: string;
  title: string;
  fileName: string;
  documentType: string;
  pages: number;
  sizeKb: number;
  uploadedAt: string;
  status: "ready" | "processing" | "failed" | "analysis_failed";
  riskScore: number;
  riskLevel: RiskLevel;
  flags: number;
  analysis?: LegalAnalysis;
}

export interface PaginatedDocumentsResponse {
  items: LexiDocument[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface UploadResponse {
  document_id: string;
  title: string;
  document_type: string;
  status: "processing" | "completed";
  pages: number;
  character_count: number;
  text_preview: string;
  storage_path: string;
  created_at: string;
  message?: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  confidence?: number;
}

export interface ChatCitation {
  clauseTitle: string;
  section: string;
  excerpt: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
}

export type ClauseSimilarity = "identical" | "similar" | "changed" | "added" | "removed";

export interface CompareSummary {
  purpose_a: string;
  purpose_b: string;
  parties_a: string;
  parties_b: string;
  agreement_type_a: string;
  agreement_type_b: string;
  effective_dates_a: string;
  effective_dates_b: string;
  expiry_a: string;
  expiry_b: string;
  jurisdiction_a: string;
  jurisdiction_b: string;
  governing_law_a: string;
  governing_law_b: string;
}

export interface CompareClause {
  clause_name: string;
  present_in_a: boolean;
  present_in_b: boolean;
  similarity: ClauseSimilarity;
  text_a: string;
  text_b: string;
  difference_explanation: string;
  additional_obligations: string;
}

export interface CompareRights {
  role: string;
  added: string[];
  removed: string[];
}

export interface CompareObligation {
  obligation: string;
  party_a: string;
  party_b: string;
  detail_a: string;
  detail_b: string;
  changed: boolean;
}

export interface CompareRisk {
  risk: string;
  severity: "high" | "medium" | "low";
  added: boolean;
  removed: boolean;
  explanation: string;
}

export interface CompareFinancial {
  term: string;
  value_a: string;
  value_b: string;
  changed: boolean;
}

export interface CompareTimeline {
  event: string;
  value_a: string;
  value_b: string;
  changed: boolean;
}

export interface CompareMissingClause {
  clause_name: string;
  missing_from: string;
  excerpt: string;
}

export interface ComparisonMetrics {
  similarity_score: number;
  total_clauses_compared: number;
  clauses_matched: number;
  clauses_changed: number;
  clauses_added: number;
  clauses_removed: number;
  similarity_justification: string;
}

export interface ComparisonResultBody {
  summary: CompareSummary;
  clauses: CompareClause[];
  rights: CompareRights[];
  obligations: CompareObligation[];
  risks: CompareRisk[];
  financials: CompareFinancial[];
  timeline: CompareTimeline[];
  missing_clauses: CompareMissingClause[];
  metrics: ComparisonMetrics | null;
}

/** Full comparison response from POST /compare — mirrors backend ComparisonResponse. */
export interface ComparisonResult {
  comparison_id: string;
  document_a_id: string;
  document_b_id: string;
  document_a_title: string;
  document_b_title: string;
  document_a_type: string;
  document_b_type: string;
  created_at: string;
  cached: boolean;
  result: ComparisonResultBody;
}

export interface ComparisonHistoryItem {
  id: string;
  document_a_id: string;
  document_b_id: string;
  user_id: string;
  result: ComparisonResultBody;
  created_at: string;
}

export interface RightArticle {
  id: string;
  category: string;
  title: string;
  summary: string;
  jurisdiction: string;
  readMinutes: number;
}
