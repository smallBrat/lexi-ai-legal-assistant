/**
 * Centralized polling registry.
 *
 * Survives component re-renders and route transitions because the
 * registry lives outside React's component tree.  Each document ID
 * owns exactly one polling loop; multiple components can subscribe
 * to the same ID without creating duplicate timers.
 *
 * Polling stops ONLY on terminal analysis states or when the last
 * subscriber unsubscribes. A stopped entry is DELETED, never
 * recreated with a live status: `getStatus` of a deleted ID returns
 * "idle" (via peekStatus) so no scheduleNext() can resurrect it.
 *
 * Lifecycle log events: POLL_START, POLL_TICK, POLL_TERMINATE,
 * POLL_STOPPED, POLL_DUPLICATE_BLOCKED.
 */

export type PollingStatus = "idle" | "polling" | "completed" | "failed";

export interface PollingEntry {
  status: PollingStatus;
  subscribers: Set<() => void>;
  intervalId: ReturnType<typeof setInterval> | null;
  timeoutId: ReturnType<typeof setTimeout> | null;
  lastError: string | null;
  lastFetchTime: number | null;
}

function pollLog(event: string, detail: Record<string, unknown>): void {
  try {

    console.info(`[lexi][polling] ${event}`, detail);
  } catch {
    // Logging must never throw.
  }
}

class PollingRegistry {
  private static instance: PollingRegistry | null = null;
  private entries: Map<string, PollingEntry> = new Map();

  private constructor() {}

  static getInstance(): PollingRegistry {
    if (!PollingRegistry.instance) {
      PollingRegistry.instance = new PollingRegistry();
    }
    return PollingRegistry.instance;
  }

  /** Get or create an entry for a document ID. */
  getEntry(documentId: string): PollingEntry {
    if (!this.entries.has(documentId)) {
      this.entries.set(documentId, {
        status: "idle",
        subscribers: new Set(),
        intervalId: null,
        timeoutId: null,
        lastError: null,
        lastFetchTime: null,
      });
    }
    return this.entries.get(documentId)!;
  }

  /** Read status WITHOUT creating an entry. Deleted IDs read as "idle". */
  peekStatus(documentId: string): PollingStatus {
    return this.entries.get(documentId)?.status ?? "idle";
  }

  /** Subscribe to updates for a document ID.  Returns unsubscribe. */
  subscribe(documentId: string, callback: () => void): () => void {
    const entry = this.getEntry(documentId);
    entry.subscribers.add(callback);
    return () => {
      entry.subscribers.delete(callback);
      this.maybeStop(documentId);
    };
  }

  /** Notify all subscribers for a document ID. */
  notify(documentId: string): void {
    const entry = this.entries.get(documentId);
    if (entry) {
      for (const cb of entry.subscribers) {
        try {
          cb();
        } catch {
          // Subscriber errors must not break the registry.
        }
      }
    }
  }

  /** Set the interval for a document ID. Only one interval per ID. */
  setInterval(documentId: string, id: ReturnType<typeof setInterval>): void {
    const entry = this.getEntry(documentId);
    if (entry.intervalId !== null) {
      clearInterval(entry.intervalId);
    }
    entry.intervalId = id;
  }

  /** Set a timeout for a document ID. */
  setTimeout(documentId: string, id: ReturnType<typeof setTimeout>): void {
    const entry = this.getEntry(documentId);
    if (entry.timeoutId !== null) {
      clearTimeout(entry.timeoutId);
    }
    entry.timeoutId = id;
  }

  /** Get the interval ID for a document ID. */
  getInterval(documentId: string): ReturnType<typeof setInterval> | null {
    return this.getEntry(documentId).intervalId;
  }

  /** Get the timeout ID for a document ID. */
  getTimeout(documentId: string): ReturnType<typeof setTimeout> | null {
    return this.getEntry(documentId).timeoutId;
  }

  /** Update the status of a document ID. */
  setStatus(documentId: string, status: PollingStatus): void {
    const entry = this.getEntry(documentId);
    entry.status = status;
    this.notify(documentId);
  }

  /**
   * Get the status of a document ID WITHOUT recreating a deleted entry.
   * Requirement 13.4-2: a deleted (stopped) entry must read as "idle" so
   * `scheduleNext()` guards see a non-"polling" status and bail out.
   */
  getStatus(documentId: string): PollingStatus {
    return this.peekStatus(documentId);
  }

  /** Record an error for a document ID. */
  setError(documentId: string, error: string | null): void {
    const entry = this.getEntry(documentId);
    entry.lastError = error;
  }

  /** Get the last error for a document ID. */
  getError(documentId: string): string | null {
    return this.getEntry(documentId).lastError;
  }

  /** Record the last fetch time. */
  setFetchTime(documentId: string, time: number): void {
    this.getEntry(documentId).lastFetchTime = time;
  }

  /** Check if a document ID has any subscribers. */
  hasSubscribers(documentId: string): boolean {
    return this.getEntry(documentId).subscribers.size > 0;
  }

  /** Stop polling if no subscribers remain. */
  private maybeStop(documentId: string): void {
    const entry = this.entries.get(documentId);
    if (!entry) return;
    if (entry.subscribers.size === 0 && entry.intervalId === null) {
      // Clean up the entry entirely when fully empty
      this.entries.delete(documentId);
    }
  }

  /** Clear any pending timers for a document ID without deleting the entry.
   *  Used to guarantee a single polling chain before a new one starts. */
  clearTimers(documentId: string): void {
    const entry = this.entries.get(documentId);
    if (!entry) return;
    if (entry.intervalId !== null) {
      clearInterval(entry.intervalId);
      entry.intervalId = null;
    }
    if (entry.timeoutId !== null) {
      clearTimeout(entry.timeoutId);
      entry.timeoutId = null;
    }
  }

  /**
   * Force stop all polling for a document ID: clears interval + timeout,
   * unsubscribes every subscriber, and DELETES the entry. After this call
   * `getStatus(id)` returns "idle" (no resurrection) until a caller
   * explicitly starts polling again via `startFresh`.
   */
  stop(documentId: string, reason: "completed" | "failed" | "auth" | "terminal" | "manual" = "manual"): void {
    const entry = this.entries.get(documentId);
    if (!entry) return;
    if (entry.intervalId !== null) {
      clearInterval(entry.intervalId);
      entry.intervalId = null;
    }
    if (entry.timeoutId !== null) {
      clearTimeout(entry.timeoutId);
      entry.timeoutId = null;
    }
    entry.subscribers.clear();
    this.entries.delete(documentId);
    pollLog("POLL_STOPPED", { documentId, reason });
  }

  /**
   * Requirement 13.4-3: the ONLY way to (re)start polling. Ensures at most
   * one timer chain per document ID — any existing chain is torn down
   * first (clearTimers + stop). Returns false when a healthy chain already
   * exists (POLL_DUPLICATE_BLOCKED), true when a fresh chain may start.
   */
  startFresh(documentId: string): boolean {
    const existing = this.entries.get(documentId);
    if (existing && existing.status === "polling" && existing.timeoutId !== null) {
      pollLog("POLL_DUPLICATE_BLOCKED", { documentId });
      return false;
    }
    this.clearTimers(documentId);
    this.stop(documentId, "manual");
    pollLog("POLL_START", { documentId });
    return true;
  }

  /** Stop all polling across all document IDs. Called on unmount. */
  stopAll(): void {
    for (const [id, entry] of this.entries) {
      if (entry.intervalId !== null) clearInterval(entry.intervalId);
      if (entry.timeoutId !== null) clearTimeout(entry.timeoutId);
      pollLog("POLL_STOPPED", { documentId: id, reason: "stopAll" });
    }
    this.entries.clear();
  }

  /** Get all active document IDs being polled. */
  getActiveIds(): string[] {
    return Array.from(this.entries.keys());
  }
}

export const pollingRegistry = PollingRegistry.getInstance();
