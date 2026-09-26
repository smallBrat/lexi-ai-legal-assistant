"""Supabase repository for persisted document comparisons.

The ``comparisons`` table is created by
``backend/migrations/20260924000000_create_comparisons.sql``. Older
environments may not have run migrations yet — every method degrades
gracefully (returns ``None`` / empty list) instead of failing the
comparison request, because the comparison itself is always computable
from the two stored analyses.
"""

from typing import Any
from uuid import UUID

from app.core.logging import error, info


class ComparisonRepositoryError(Exception):
    """Raised when a comparison database operation fails unexpectedly."""


def _ordered_pair(a_id: UUID, b_id: UUID) -> tuple[str, str]:
    """Return the canonical (document_a_id, document_b_id) ordering.

    Comparisons are order-independent for caching: (A, B) and (B, A)
    resolve to the same stored row.
    """
    first, second = sorted((str(a_id), str(b_id)))
    return first, second


class ComparisonRepository:
    """Encapsulate all PostgreSQL access for comparisons."""

    def __init__(self, client: Any) -> None:
        """Initialize the repository with a Supabase client."""
        self._client = client

    def find_cached(self, a_id: UUID, b_id: UUID, user_id: str) -> dict[str, Any] | None:
        """Return the newest cached comparison for the pair, if any."""
        first, second = _ordered_pair(a_id, b_id)
        try:
            response = (
                self._client.table("comparisons")
                .select("*")
                .eq("user_id", user_id)
                .eq("document_a_id", first)
                .eq("document_b_id", second)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            records = response.data or []
            if records:
                info("Comparison cache hit", document_a_id=first, document_b_id=second)
            return records[0] if records else None
        except Exception as exc:  # noqa: BLE001 - missing table must degrade to a cache miss
            # Missing table (migrations not run) or transient failure:
            # log and treat as a cache miss so the request still succeeds.
            error("Comparison cache lookup failed", error=str(exc))
            return None

    def save(
        self,
        a_id: UUID,
        b_id: UUID,
        user_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Persist a comparison and return the stored row (or None)."""
        first, second = _ordered_pair(a_id, b_id)
        try:
            response = (
                self._client.table("comparisons")
                .insert(
                    {
                        "document_a_id": first,
                        "document_b_id": second,
                        "user_id": user_id,
                        "result": result,
                    }
                )
                .select("*")
                .execute()
            )
            records = response.data or []
            return records[0] if records else None
        except Exception as exc:  # noqa: BLE001 - persistence must never fail the request
            error("Comparison persistence failed", error=str(exc))
            return None

    def list_for_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return the user's most recent comparisons."""
        try:
            response = (
                self._client.table("comparisons")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(response.data or [])
        except Exception as exc:  # noqa: BLE001 - history must degrade to empty, not 503
            error("Comparison history lookup failed", error=str(exc))
            return []
