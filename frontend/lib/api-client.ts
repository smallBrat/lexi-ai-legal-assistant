import { getSupabaseBrowserClient } from "@/lib/supabase";
import {
  CHAT_HISTORY_TIMEOUT_MS,
  CHAT_REQUEST_TIMEOUT_MS,
  DEFAULT_TIMEOUT_MS,
  DOCUMENT_FETCH_TIMEOUT_MS,
} from "@/lib/request-timeouts";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export { CHAT_HISTORY_TIMEOUT_MS, CHAT_REQUEST_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, DOCUMENT_FETCH_TIMEOUT_MS };

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

type RequestOptions = {
  signal?: AbortSignal;
  /** Override the default 30s timeout (ms). `0` disables the timeout. */
  timeoutMs?: number;
};

function parseErrorMessage(body: unknown): string {
  if (body !== null && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((entry) =>
          entry !== null && typeof entry === "object" && "msg" in entry
            ? String((entry as { msg: unknown }).msg)
            : null,
        )
        .filter((m): m is string => Boolean(m));
      if (messages.length > 0) return messages.join("; ");
    }
  }
  return "Request failed.";
}

/** Combine a caller signal with a timeout into one AbortSignal. */
function withTimeout(signal: AbortSignal | undefined, timeoutMs: number): {
  signal: AbortSignal | undefined;
  cancel: () => void;
} {
  if (timeoutMs <= 0) return { signal, cancel: () => undefined };
  const controller = new AbortController();
  const timer = setTimeout(() => {
    const reason = new DOMException("Request timed out.", "TimeoutError");
    controller.abort(reason);
  }, timeoutMs);
  if (signal) {
    if (signal.aborted) {
      clearTimeout(timer);
      controller.abort(signal.reason);
    } else {
      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        controller.abort(signal.reason);
      }, { once: true });
    }
  }
  return { signal: controller.signal, cancel: () => clearTimeout(timer) };
}

async function getAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const { data } = await getSupabaseBrowserClient().auth.getSession();
  return data.session?.access_token ?? null;
}

/**
 * Phase 14.3 — single-flight Supabase token refresh.
 *
 * Requirements:
 *   1. Callers can check expiry and refresh PROACTIVELY (60s window).
 *   4. Never two simultaneous refreshes — every caller awaits the SAME
 *      in-flight refresh promise.
 *   5. Waiting requests queue behind one refresh; each gets the fresh
 *      token when it settles.
 *
 * Implementation: a module-level promise is created by the first caller
 * that needs a refresh; all concurrent callers await that same promise.
 * The slot is cleared when it settles so a LATER expiry can refresh again.
 */
let refreshInFlight: Promise<string | null> | null = null;

/** Refresh the Supabase session exactly once and return the new access token. */
function beginRefresh(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const { data, error } = await getSupabaseBrowserClient().auth.refreshSession();
      if (error) return null;
      return data.session?.access_token ?? null;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/**
 * Return a valid access token, refreshing proactively when the current
 * session expires within `horizonMs` (default 60s). Concurrent callers
 * during one expiry window share a single refresh request.
 */
export async function getValidAccessToken(horizonMs = 60_000): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const supabase = getSupabaseBrowserClient();
  const { data } = await supabase.auth.getSession();
  const session = data.session;

  if (!session?.access_token) return null;

  const expiresAtMs = (session.expires_at ?? 0) * 1000;
  const expiresIn = expiresAtMs - Date.now();
  if (expiresIn > horizonMs) return session.access_token; // still fresh

  // Expiring within the horizon (or already expired): refresh (single-flight).
  const token = await beginRefresh();
  if (token) return token;
  // Refresh failed — fall back to whatever session exists; the request will
  // 401 and the caller-side single retry handles it.
  return session.access_token;
}

/**
 * Get a fresh Supabase session: returns the current token if it is valid
 * beyond the 60s proactive window, otherwise refreshes once (single-flight).
 * Returns null on failure.
 */
export async function getFreshSession(): Promise<{ access_token: string } | null> {
  if (typeof window === "undefined") return null;
  try {
    const token = await getValidAccessToken();
    return token ? { access_token: token } : null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}, options: RequestOptions = {}): Promise<T> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const combined = withTimeout(options.signal ?? init.signal ?? undefined, timeoutMs);

  async function send(currentHeaders: Headers): Promise<Response> {
    try {
      return await fetch(`${API_URL}${path}`, { ...init, headers: currentHeaders, signal: combined.signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ApiError(0, "Request timed out. Please try again.", { path });
      }
      throw error instanceof Error ? error : new Error("Network request failed.");
    }
  }

  try {
    let response = await send(headers);
    if (response.status === 401 && typeof window !== "undefined") {
      // Reactive fallback: single-flight refresh shared with pollingFetch.
      const fresh = await beginRefresh();
      if (fresh) {
        headers.set("Authorization", `Bearer ${fresh}`);
        response = await send(headers);
      }
    }

    const body = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(response.status, parseErrorMessage(body), body);
    }
    return body as T;
  } catch (error) {
    throw error;
  } finally {
    combined.cancel();
  }
}

/** Execute a request with a proactive-checked JWT token, auto-refreshing on 401.
 *  Designed for polling loops: validates session expiry (60s horizon) before
 *  every call and shares one refresh across concurrent requests. */
export async function pollingFetch<T>(path: string, init: RequestInit = {}, options: RequestOptions = {}): Promise<T> {
  const token = await getValidAccessToken();
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const timeoutMs = options.timeoutMs ?? DOCUMENT_FETCH_TIMEOUT_MS;
  const combined = withTimeout(options.signal ?? init.signal ?? undefined, timeoutMs);

  async function send(currentHeaders: Headers): Promise<Response> {
    try {
      return await fetch(`${API_URL}${path}`, { ...init, headers: currentHeaders, signal: combined.signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ApiError(0, "Request timed out. Please try again.", { path });
      }
      throw error instanceof Error ? error : new Error("Network request failed.");
    }
  }

  try {
    let response = await send(headers);
    if (response.status === 401) {
      // Reactive fallback: refresh once (single-flight) and retry once.
      const fresh = await beginRefresh();
      if (fresh) {
        headers.set("Authorization", `Bearer ${fresh}`);
        response = await send(headers);
      }
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(response.status, parseErrorMessage(body), body);
    }
    return body as T;
  } catch (error) {
    throw error;
  } finally {
    combined.cancel();
  }
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) =>
    // GET sends no body and therefore no Content-Type.
    request<T>(path, { signal: options?.signal }, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => {
    const init: RequestInit = { method: "POST", signal: options?.signal };
    // Only send a body when one is explicitly provided.  Sending
    // "{}" (the old `JSON.stringify(undefined ?? {})` behavior)
    // makes FastAPI validate a stray JSON body for endpoints whose
    // parameters are Query-only, which returns 422 before the
    // handler ever runs.
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }
    return request<T>(path, init, options);
  },
  upload: <T>(path: string, formData: FormData, onProgress?: (progress: number) => void) =>
    new Promise<T>((resolve, reject) => {
      void getAccessToken().then((token) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_URL}${path}`);
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
        };
        xhr.onload = () => {
          let body: (T & { detail?: string }) | null = null;
          try {
            body = JSON.parse(xhr.responseText || "null") as T & { detail?: string };
          } catch {
            reject(new ApiError(xhr.status, "Upload failed: invalid server response.", xhr.responseText));
            return;
          }
          if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
          else reject(new ApiError(xhr.status, body?.detail ?? "Upload failed.", body));
        };
        xhr.onerror = () => reject(new ApiError(0, "Network request failed."));
        xhr.send(formData);
      }).catch(reject);
    }),
};
