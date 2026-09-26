/**
 * Canonical document-ID validation layer (PART 7).
 *
 * The backend declares `document_id: UUID` path params, so any non-UUID id
 * fails FastAPI request validation with 422 before the handler runs. Every
 * page must validate route/search params through these helpers BEFORE
 * creating a query or emitting a request:
 *
 *   - `isValidDocumentId(id)` — boolean gate for `enabled` flags.
 *   - `parseDocumentId(value)` — normalizes `useParams()` output
 *     (string | string[] | undefined) to a single string.
 *   - `assertValidDocumentId(id)` — throws a typed `ApiError(422)` without
 *     touching the network, mirroring the server contract.
 *
 * Invalid UUIDs render a UI error and never send a request.
 */
import { ApiError } from "@/lib/api-client";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isValidDocumentId(documentId: string): boolean {
  return UUID_RE.test(documentId);
}

/** Normalize a Next.js route param (`string | string[] | undefined`) to one string. */
export function parseDocumentId(
  value: string | string[] | undefined | null,
): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/**
 * Throw a typed 422 `ApiError` for non-UUID ids without touching the
 * network. Use inside query/mutation functions as a fail-fast guard.
 */
export function assertValidDocumentId(documentId: string): asserts documentId is string {
  if (!isValidDocumentId(documentId)) {
    throw new ApiError(422, "Invalid document ID: expected a UUID.", {
      loc: ["path", "document_id"],
    });
  }
}
