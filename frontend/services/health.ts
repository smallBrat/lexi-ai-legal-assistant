/**
 * Backend health check.
 *
 * Always targets the backend at `NEXT_PUBLIC_API_URL + "/health"` — never a
 * relative `/health` (that would hit the Next.js dev server on
 * localhost:3000, which has no such route and answers 404). If the API URL
 * is unavailable, the check is skipped gracefully instead of failing.
 */

export interface BackendHealth {
  status: string;
  service: string;
}

function getBackendBaseUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/$/, "");
}

export async function checkBackendHealth(
  signal?: AbortSignal,
): Promise<BackendHealth | null> {
  const baseUrl = getBackendBaseUrl();
  if (baseUrl === null) return null;
  try {
    const response = await fetch(`${baseUrl}/health`, { signal });
    if (!response.ok) return null;
    const body = (await response.json().catch(() => null)) as BackendHealth | null;
    if (body === null || typeof body.status !== "string") return null;
    return body;
  } catch {
    return null;
  }
}
