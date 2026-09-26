/**
 * Persistent polling hook with exponential backoff (Phase 14.1 — FINAL).
 *
 * - Independent polling per document ID; at most ONE timer chain per ID.
 * - Polling survives component re-render and route transitions
 *   (registry lives outside React).
 * - TERMINAL states (ready+analysis, analysis_completed, failed,
 *   analysis_failed) trigger a SYNCHRONOUS, unbypassable hard stop:
 *     1. mountedRef.current = false      (in-flight continuation bails)
 *     2. registry status -> terminal     (subscribers notified)
 *     3. pollingRegistry.stop(id,"terminal")  (timers cleared, entry deleted)
 *     4. unsubscribe()
 *     5. local timeout refs cleared
 *     6. return immediately — scheduleNext() can NEVER run afterward:
 *        the timer was cleared, the entry is deleted, and scheduleNext
 *        re-checks peekStatus(id) !== "polling" before creating a timeout.
 * - Duplicate-loop prevention: every (re)start goes through
 *   pollingRegistry.startFresh(); a healthy existing chain logs
 *   POLL_DUPLICATE_BLOCKED instead of spawning a second chain.
 * - Auth safety: on 401 refresh ONCE, retry ONCE; failure stops polling.
 * - React Query is NOT a network source: poll results are pushed into the
 *   cache with queryClient.setQueryData(["document", id], result) so
 *   useDocument never needs its own fetch (QUERY_FETCH logged on the
 *   one-shot post-analyze invalidation only).
 *
 * Logs: POLL_START, POLL_TICK, POLL_TERMINATE, POLL_STOPPED,
 * POLL_DUPLICATE_BLOCKED (registry) — all with documentId + timestamp.
 */

"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { pollingGetDocument } from "@/services/documents";
import { isValidDocumentId } from "@/lib/document-id";
import { pollingRegistry } from "@/lib/polling-registry";
import { getFreshSession } from "@/lib/api-client";
import type { LexiDocument } from "@/types";

const BACKOFF_INTERVALS = [2000, 4000, 6000, 6000, 8000];
const MAX_INTERVAL = 8000;

interface UsePollingOptions {
  documentId: string;
  onStatusChange?: (status: string, analysisPresent: boolean) => void;
}

function pollLog(event: string, detail: Record<string, unknown>): void {
  try {
     
    console.info(`[lexi][polling] ${event}`, { at: new Date().toISOString(), ...detail });
  } catch {
    // Logging must never throw.
  }
}

/** Terminal-state predicate: these statuses end polling permanently. */
function isTerminalStatus(status: string, analysisPresent: boolean): boolean {
  return (
    (status === "ready" && analysisPresent) ||
    status === "analysis_completed" ||
    status === "failed" ||
    status === "analysis_failed"
  );
}

export function usePolling({ documentId, onStatusChange }: UsePollingOptions) {
  const valid = isValidDocumentId(documentId);
  const queryClient = useQueryClient();
  const [document, setDocument] = useState<LexiDocument | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const backoffIndexRef = useRef(0);
  const mountedRef = useRef(true);
  const inFlightRef = useRef(false);
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const documentIdRef = useRef(documentId);

  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  /**
   * Phase 14.1: SYNCHRONOUS hard stop — every step runs immediately, in
   * order, with no awaits, so no code path can observe a half-stopped
   * state or re-arm a timer afterward.
   */
  const terminatePolling = useCallback(
    (reason: "completed" | "failed" | "auth_failed") => {
      // (1) Kill the continuation flag first: any in-flight fetch promise
      //     that resolves after this point bails at its mountedRef check.
      mountedRef.current = false;
      // (2) Terminal status while the entry still exists (notifies subscribers).
      pollingRegistry.setStatus(documentId, reason === "auth_failed" ? "failed" : reason);
      // (3) Clear interval + timeout, drop all subscribers, DELETE the entry.
      //     After this, peekStatus(id) === "idle" forever until startFresh.
      pollingRegistry.stop(documentId, reason === "auth_failed" ? "auth" : "terminal");
      // (4) Unsubscribe this hook's registry listener.
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
      // (5) Clear any local timeout ref (belt-and-braces with registry stop).
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      backoffIndexRef.current = 0;
      inFlightRef.current = false;
      setIsPolling(false);
      // (6) Return — caller returns immediately; no scheduleNext() possible.
      pollLog("POLL_TERMINATE", { documentId, reason });
    },
    [documentId],
  );

  const handleResult = useCallback(
    (result: LexiDocument): boolean => {
      setDocument(result);
      setError(null);
      backoffIndexRef.current = 0;
      pollingRegistry.setFetchTime(documentId, Date.now());

      const analysisPresent = result.analysis != null;
      const terminal = isTerminalStatus(result.status, analysisPresent);

      if (terminal) {
        const reason = result.status === "failed" || result.status === "analysis_failed" ? "failed" : "completed";
        // Push into React Query cache so useDocument shows the terminal
        // document without issuing its own GET (Phase 14.1 req. 5).
        queryClient.setQueryData(["document", documentId], result);
        terminatePolling(reason);
      } else {
        pollingRegistry.setStatus(documentId, "polling");
        // Keep the cache warm for non-terminal results too — useQuery is
        // disabled while polling, so this IS its data source.
        queryClient.setQueryData(["document", documentId], result);
      }

      onStatusChangeRef.current?.(result.status, analysisPresent);
      return terminal;
    },
    [documentId, terminatePolling, queryClient],
  );

  const stableFetchDocument = useCallback(async () => {
    if (!valid || inFlightRef.current) return;
    inFlightRef.current = true;
    pollLog("POLL_TICK", { documentId });

    try {
      const result = await pollingGetDocument(documentId);
      if (!mountedRef.current || pollingRegistry.peekStatus(documentId) !== "polling") return;
      handleResult(result);
    } catch (err: unknown) {
      if (!mountedRef.current || pollingRegistry.peekStatus(documentId) !== "polling") return;

      const status = err instanceof Error && "status" in err ? (err as { status: number }).status : 0;
      const isTransient =
        status >= 500 ||
        status === 0 ||
        err instanceof DOMException ||
        (err instanceof Error && err.message.includes("timeout"));

      if (isTransient) {
        // Transient backend errors keep polling with backoff (unchanged).
        setIsReconnecting(true);
        setError("Backend busy...");
        backoffIndexRef.current = Math.min(backoffIndexRef.current + 1, 4);
      } else if (status === 401) {
        // Phase 14.3 (production): the ONLY reactive 401 path left. It
        // should be rare — pollingFetch refreshes proactively 60s before
        // expiry — but if the backend still rejects the token we:
        //   1. join the shared single-flight refresh (never a second one),
        //   2. retry the fetch EXACTLY ONCE with the fresh token,
        //   3. terminate polling gracefully if refresh or retry fails —
        //      no loop, no repeated 401s.
        // Note: the retry goes through pollingGetDocument, whose own
        // getValidAccessToken() sees the already-fresh session and does
        // NOT trigger another refresh.
        setError("Refreshing session...");
        try {
          await getFreshSession();
          const retry = await pollingGetDocument(documentId);
          if (!mountedRef.current || pollingRegistry.peekStatus(documentId) !== "polling") return;
          handleResult(retry);
        } catch {
          // Refresh or retry failed: stop polling gracefully and for good.
          setError("Authentication expired. Please refresh.");
          terminatePolling("auth_failed");
        }
      } else {
        setError(err instanceof Error ? err.message : "Failed to fetch document.");
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [documentId, valid, handleResult, terminatePolling]);

  useEffect(() => {
    if (!valid) return;
    mountedRef.current = true;
    documentIdRef.current = documentId;

    // Exactly one timer chain per document ID: startFresh tears down any
    // previous chain (clearTimers + stop) and logs POLL_START / or blocks a
    // duplicate with POLL_DUPLICATE_BLOCKED.
    const canStart = pollingRegistry.startFresh(documentId);

    // Clean up previous subscription if documentId changed
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }

    // Subscribe to registry updates
    unsubscribeRef.current = pollingRegistry.subscribe(documentId, () => {
      if (mountedRef.current && documentIdRef.current === documentId) {
        setIsPolling(pollingRegistry.peekStatus(documentId) === "polling");
      }
    });

    if (canStart) {
      pollingRegistry.setStatus(documentId, "polling");
      setIsPolling(true);
      setIsReconnecting(false);

      void stableFetchDocument();

      const scheduleNext = (): void => {
        // Gate 1: unmount or terminal already processed.
        if (!mountedRef.current) return;
        // Gate 2 (Phase 14.1 req. 3): peekStatus — does NOT create an
        // entry. Anything other than "polling" (including "idle" for a
        // deleted entry) means stopped; never create a timeout.
        if (pollingRegistry.peekStatus(documentId) !== "polling") {
          setIsPolling(false);
          pollLog("POLL_STOPPED", { documentId, at: "scheduleNext", status: pollingRegistry.peekStatus(documentId) });
          return;
        }
        const interval = Math.min(
          BACKOFF_INTERVALS[Math.min(backoffIndexRef.current, BACKOFF_INTERVALS.length - 1)],
          MAX_INTERVAL,
        );
        const id = setTimeout(() => {
          if (!mountedRef.current || pollingRegistry.peekStatus(documentId) !== "polling") return;
          void stableFetchDocument().finally(scheduleNext);
        }, interval);
        timeoutRef.current = id;
        pollingRegistry.setTimeout(documentId, id);
      };

      scheduleNext();
    } else {
      // Duplicate start blocked: the existing chain keeps polling.
      setIsPolling(true);
      setIsReconnecting(false);
    }

    return () => {
      mountedRef.current = false;
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
    };
  }, [documentId, valid, stableFetchDocument]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return { document, isPolling, error, isReconnecting };
}
