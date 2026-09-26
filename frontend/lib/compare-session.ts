/**
 * Compare session persistence using sessionStorage.
 *
 * Persists:
 * - documentA.id
 * - documentB.id
 * - upload status
 * - analysis status
 * - titles
 *
 * On page load, restores the compare session and automatically
 * resumes polling for unfinished documents.
 *
 * If the browser refreshes mid-analysis, the user continues
 * exactly where they left off.
 */

export interface CompareSessionData {
  documentAId: string | null;
  documentBId: string | null;
  documentATitle: string | null;
  documentBTitle: string | null;
  documentAStatus: string | null;
  documentBStatus: string | null;
  documentAAnalysisPresent: boolean;
  documentBAnalysisPresent: boolean;
  readyA: boolean;
  readyB: boolean;
  lastUpdated: number;
}

export interface CompareSessionDataInput {
  documentAId?: string | null;
  documentBId?: string | null;
  documentATitle?: string | null;
  documentBTitle?: string | null;
  documentAStatus?: string | null;
  documentBStatus?: string | null;
  documentAAnalysisPresent?: boolean;
  documentBAnalysisPresent?: boolean;
  readyA?: boolean;
  readyB?: boolean;
}

const STORAGE_KEY = "lexi_compare_session";
const MAX_AGE_MS = 30 * 60 * 1000; // 30 minutes max age

export function saveCompareSession(data: CompareSessionDataInput): void {
  try {
    if (typeof window === "undefined") return;
    const existing = loadCompareSession();
    const filtered: CompareSessionDataInput = {};
    for (const [key, value] of Object.entries(data)) {
      if (value !== undefined) filtered[key as keyof CompareSessionDataInput] = value;
    }
    const merged: CompareSessionData = {
      ...existing,
      ...(filtered as CompareSessionData),
      lastUpdated: Date.now(),
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // sessionStorage may be full or unavailable
  }
}

export function loadCompareSession(): CompareSessionData | null {
  try {
    if (typeof window === "undefined") return null;
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data: CompareSessionData = JSON.parse(raw);
    // Check if session has expired
    if (Date.now() - data.lastUpdated > MAX_AGE_MS) {
      clearCompareSession();
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function clearCompareSession(): void {
  try {
    if (typeof window === "undefined") return;
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
}

export function hasValidCompareSession(): boolean {
  const session = loadCompareSession();
  if (!session) return false;
  // Must have at least one document ID and recent activity
  return (session.documentAId != null || session.documentBId != null) && Date.now() - session.lastUpdated < MAX_AGE_MS;
}

export function serializeCompareState(data: CompareSessionData): object {
  return {
    documentAId: data.documentAId,
    documentBId: data.documentBId,
    documentATitle: data.documentATitle,
    documentBTitle: data.documentBTitle,
    documentAStatus: data.documentAStatus,
    documentBStatus: data.documentBStatus,
    documentAAnalysisPresent: data.documentAAnalysisPresent,
    documentBAnalysisPresent: data.documentBAnalysisPresent,
    readyA: data.readyA,
    readyB: data.readyB,
  };
}
