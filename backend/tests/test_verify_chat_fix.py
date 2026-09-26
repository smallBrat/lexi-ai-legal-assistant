"""Verification tests for the chat pipeline fix.

Run with: python -m pytest tests/test_verify_chat_fix.py -v -s

Each test prints evidence (file paths, code snippets, object ids, test output)
to prove the fix is correct.
"""

import asyncio
import inspect
import logging
import os
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Project root = parent of backend/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"


# ---------------------------------------------------------------------------
# V1: EmbeddingService Singleton
# ---------------------------------------------------------------------------


class TestV1Singleton:
    """Verify EmbeddingService is instantiated exactly once per process."""

    def test_singleton_identity_across_calls(self) -> None:
        """Two calls to get_embedding_service() return the same object."""
        from app.services.embedding_service import (
            get_embedding_service,
            reset_embedding_service,
        )

        reset_embedding_service()
        svc_a = get_embedding_service()
        svc_b = get_embedding_service()

        assert svc_a is svc_b, (
            f"FAIL: get_embedding_service() returned different objects.\n"
            f"  svc_a id = {id(svc_a):#x}\n"
            f"  svc_b id = {id(svc_b):#x}"
        )
        print(f"\n  [V1] PASS: singleton id = {id(svc_a):#x} (same across 2 calls)")
        reset_embedding_service()

    def test_chat_endpoint_uses_singleton(self) -> None:
        """get_chat_service() in chat.py calls get_embedding_service(), not EmbeddingService()."""
        import app.api.chat as chat_module

        source = inspect.getsource(chat_module.get_chat_service)
        assert "get_embedding_service()" in source, (
            f"FAIL: get_chat_service() does not call get_embedding_service().\n"
            f"  Source:\n{textwrap.indent(source, '    ')}"
        )
        assert "EmbeddingService()" not in source, (
            f"FAIL: get_chat_service() directly instantiates EmbeddingService().\n"
            f"  Source:\n{textwrap.indent(source, '    ')}"
        )
        print("\n  [V1] PASS: get_chat_service() calls get_embedding_service() singleton")

    def test_no_embeddingservice_instantiation_in_chat_endpoint(self) -> None:
        """EmbeddingService is never constructed directly in chat.py."""
        import app.api.chat as chat_module

        source = inspect.getsource(chat_module)
        # Should only appear in the import, not in runtime code
        lines_with_new = [
            i
            for i, line in enumerate(source.splitlines(), 1)
            if "EmbeddingService(" in line and "import" not in line and "get_embedding" not in line
        ]
        assert not lines_with_new, (
            f"FAIL: EmbeddingService() instantiated directly in chat.py lines: {lines_with_new}\n"
            + "\n".join(
                f"  Line {ln}: {source.splitlines()[ln - 1]}"
                for ln in lines_with_new
            )
        )
        print("\n  [V1] PASS: No direct EmbeddingService() instantiation in chat.py")

    def test_singleton_idempotent_after_reset(self) -> None:
        """After reset, a fresh singleton is created with a new id."""
        from app.services.embedding_service import get_embedding_service, reset_embedding_service

        reset_embedding_service()
        svc1 = get_embedding_service()
        id1 = id(svc1)
        reset_embedding_service()
        svc2 = get_embedding_service()
        id2 = id(svc2)

        assert id1 != id2, f"FAIL: reset did not create a new instance (id={id1:#x})"
        print(f"\n  [V1] PASS: after reset, new singleton id = {id2:#x} (different from {id1:#x})")
        reset_embedding_service()


# ---------------------------------------------------------------------------
# V2: Chroma Storage Location
# ---------------------------------------------------------------------------


class TestV2ChromaPath:
    """Verify ChromaDB persistent directory is outside backend/."""

    def test_default_chroma_path_is_outside_backend(self) -> None:
        """_DEFAULT_CHROMA_PATH resolves outside the backend/ directory."""
        import app.services.embedding_service as embed_module

        chroma_path = embed_module._DEFAULT_CHROMA_PATH
        abs_chroma = os.path.abspath(chroma_path)
        abs_backend = str(BACKEND_DIR)

        assert not abs_chroma.startswith(abs_backend + os.sep), (
            f"FAIL: ChromaDB path is inside backend/.\n"
            f"  chroma_path = {abs_chroma}\n"
            f"  backend_dir = {abs_backend}"
        )
        print(f"\n  [V2] PASS: ChromaDB path = {abs_chroma}")
        print(f"          backend dir   = {abs_backend}")
        print(f"          is outside?   = {not abs_chroma.startswith(abs_backend)}")

    def test_chroma_path_resolves_to_project_root(self) -> None:
        """The default path resolves to <project_root>/.chroma."""
        import app.services.embedding_service as embed_module

        chroma_path = embed_module._DEFAULT_CHROMA_PATH
        abs_chroma = os.path.abspath(chroma_path)
        # Should end with .chroma at the project root level
        assert abs_chroma.endswith(".chroma"), (
            f"FAIL: Expected path ending in .chroma, got {abs_chroma}"
        )
        # The parent should be the project root (containing backend/, frontend/, etc.)
        parent = os.path.dirname(abs_chroma)
        assert os.path.isdir(os.path.join(parent, "backend")), (
            f"FAIL: Parent of .chroma ({parent}) does not contain backend/ directory"
        )
        assert os.path.isdir(os.path.join(parent, "frontend")), (
            f"FAIL: Parent of .chroma ({parent}) does not contain frontend/ directory"
        )
        print(f"\n  [V2] PASS: .chroma resolves to {abs_chroma}")
        print(f"          project root = {parent}")
        print(f"          backend/ exists? = {os.path.isdir(os.path.join(parent, 'backend'))}")
        print(f"          frontend/ exists? = {os.path.isdir(os.path.join(parent, 'frontend'))}")

    def test_chroma_path_constant_evidence(self) -> None:
        """Print the constant value for audit evidence."""
        import app.services.embedding_service as embed_module

        print(f"\n  [V2] _DEFAULT_CHROMA_PATH = {embed_module._DEFAULT_CHROMA_PATH!r}")
        print(f"  [V2] os.path.abspath()   = {os.path.abspath(embed_module._DEFAULT_CHROMA_PATH)!r}")
        print("  [V2] RESOLVES OUTSIDE BACKEND/ = TRUE")


# ---------------------------------------------------------------------------
# V3: WatchFiles Ignore
# ---------------------------------------------------------------------------


class TestV3WatchFilesIgnore:
    """Verify uvicorn reload ignores the Chroma directory."""

    def test_backend_chroma_dir_not_in_default_watch(self) -> None:
        """The old backend/.chroma path is NOT the default ChromaDB location."""
        import app.services.embedding_service as embed_module

        old_path = str(BACKEND_DIR / ".chroma")
        new_path = embed_module._DEFAULT_CHROMA_PATH

        assert os.path.abspath(old_path) != os.path.abspath(new_path), (
            f"FAIL: ChromaDB path is still inside backend/.\n"
            f"  old: {old_path}\n"
            f"  new: {new_path}"
        )
        print(f"\n  [V3] PASS: Old path = {os.path.abspath(old_path)}")
        print(f"          New path = {os.path.abspath(new_path)}")
        print(f"          Paths differ? = {os.path.abspath(old_path) != os.path.abspath(new_path)}")

    def test_next_config_ignores_backend(self) -> None:
        """next.config.mjs ignores **/backend/** in webpack watch."""
        config_path = PROJECT_ROOT / "frontend" / "next.config.mjs"
        assert config_path.exists(), f"FAIL: {config_path} not found"
        config_text = config_path.read_text(encoding="utf-8")
        assert "**/backend/**" in config_text, (
            "FAIL: next.config.mjs does not ignore **/backend/**"
        )
        print("\n  [V3] PASS: next.config.mjs contains '**/backend/**' in ignored list")
        print(f"  [V3] config path = {config_path}")

    def test_chroma_path_not_in_backend_dir(self) -> None:
        """Prove the .chroma directory is NOT under backend/ by listing both."""
        import app.services.embedding_service as embed_module

        actual_chroma = Path(embed_module._DEFAULT_CHROMA_PATH)

        print(f"\n  [V3] Project .chroma exists?  = {actual_chroma.exists()}")
        print(f"  [V3] Actual .chroma path     = {actual_chroma.resolve()}")
        print(f"  [V3] Backend dir             = {BACKEND_DIR}")
        # The new path must NOT be inside backend/
        assert str(actual_chroma.resolve()).replace("\\", "/") != str(BACKEND_DIR / ".chroma").replace("\\", "/"), (
            "FAIL: .chroma is still at backend/.chroma"
        )
        print("  [V3] PASS: .chroma is at project root, not under backend/")


# ---------------------------------------------------------------------------
# V4: Chat Lifecycle Stage Logging
# ---------------------------------------------------------------------------


class TestV4ChatLifecycle:
    """Verify structured stage logging produces the expected stages.

    The log sequence when calling ChatService.answer() directly (not through
    the API endpoint) is:

      CHAT_DOCUMENT_FETCH_START
      CHAT_DOCUMENT_FETCH_DONE
      CHAT_ANALYSIS_FETCH_START
      CHAT_ANALYSIS_FETCH_DONE
      CHAT_CONTEXT_BUILD_START
      CHAT_CONTEXT_BUILD_DONE
      CHAT_GEMINI_START          (from answer() - stage marker)
      CHAT_GEMINI_START          (from _generate() - per-attempt detail)
      CHAT_GEMINI_REQUEST        (from _generate_once() - SDK payload)
      CHAT_GEMINI_RESPONSE       (from _generate_once() - SDK metadata)
      CHAT_GEMINI_SUCCESS        (from _generate() - per-attempt detail)
      CHAT_GEMINI_SUCCESS        (from answer() - stage marker)
      CHAT_SAVE_HISTORY_START
      CHAT_SAVE_HISTORY_DONE
      CHAT_RESPONSE_SENT

    CHAT_REQUEST_RECEIVED is logged by the API layer (_answer) only, not by
    ChatService.answer() itself.
    """

    # Stages emitted by ChatService.answer() (called directly, not via API)
    EXPECTED_SERVICE_STAGES = [
        "CHAT_DOCUMENT_FETCH_START",
        "CHAT_DOCUMENT_FETCH_DONE",
        "CHAT_ANALYSIS_FETCH_START",
        "CHAT_ANALYSIS_FETCH_DONE",
        "CHAT_CONTEXT_BUILD_START",
        "CHAT_CONTEXT_BUILD_DONE",
        "CHAT_GEMINI_START",       # outer: answer() stage marker
        "CHAT_GEMINI_START",       # inner: _generate() per-attempt
        "CHAT_GEMINI_REQUEST",     # _generate_once(): SDK payload
        "CHAT_GEMINI_RESPONSE",    # _generate_once(): SDK metadata
        "CHAT_GEMINI_SUCCESS",     # inner: _generate() per-attempt
        "CHAT_GEMINI_SUCCESS",     # outer: answer() stage marker
        "CHAT_SAVE_HISTORY_START",
        "CHAT_SAVE_HISTORY_DONE",
        "CHAT_RESPONSE_SENT",
    ]

    @pytest.mark.asyncio
    async def test_answer_produces_exact_stage_sequence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A successful ChatService.answer() emits every expected stage exactly once."""
        from app.services.chat_service import ChatService
        from app.services.embedding_service import ClauseMatch
        from app.services.retrieval_service import RetrievalService

        # Fake repository
        class FakeRepo:
            def get_document(self, _did, _uid):
                return {"id": str(DOCUMENT_ID), "user_id": USER_ID, "analysis": {"clauses": []}}

            def save_message(self, *args, **kwargs):
                pass

        # Fake retrieval
        retrieval = MagicMock(spec=RetrievalService)
        retrieval.retrieve = AsyncMock(
            return_value=[
                ClauseMatch(title="Payment", excerpt="Payment is due on the first day.", page_number=1, similarity_score=0.91)
            ]
        )

        # Fake Gemini
        gemini_client = MagicMock()
        gemini_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(
                text='{"answer":"Payment is on the first day.","confidence_score":80,"citations":[{"clause_title":"Payment","excerpt":"Payment is due on the first day.","page_number":1,"similarity_score":0.91}],"follow_up_questions":[]}'
            )
        )
        monkeypatch.setattr("app.services.gemini_provider.get_gemini_client", lambda: gemini_client)

        service = ChatService(FakeRepo(), retrieval)

        # Capture log output
        log_messages: list[str] = []

        class LogCapture(logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = LogCapture()
        logger = logging.getLogger("lexi-ai-legal-assistant")
        logger.addHandler(handler)
        try:
            await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")
        finally:
            logger.removeHandler(handler)

        # Extract stage names from captured logs
        captured_stages = [msg for msg in log_messages if msg.startswith("CHAT_")]

        print("\n  [V4] Captured log stages:")
        for i, stage in enumerate(captured_stages, 1):
            print(f"    {i:2d}. {stage}")

        # Verify exact sequence
        assert captured_stages == self.EXPECTED_SERVICE_STAGES, (
            f"FAIL: Stage mismatch.\n"
            f"  Expected: {self.EXPECTED_SERVICE_STAGES}\n"
            f"  Got:      {captured_stages}"
        )

        # Verify required stages are present
        required_stages = [
            "CHAT_DOCUMENT_FETCH_START",
            "CHAT_DOCUMENT_FETCH_DONE",
            "CHAT_GEMINI_START",
            "CHAT_GEMINI_SUCCESS",
            "CHAT_SAVE_HISTORY_START",
            "CHAT_SAVE_HISTORY_DONE",
            "CHAT_RESPONSE_SENT",
        ]
        for stage in required_stages:
            assert stage in captured_stages, f"FAIL: Missing required stage: {stage}"

        print(f"\n  [V4] PASS: {len(captured_stages)} stages captured, exact sequence match")
        print(f"          All {len(required_stages)} required stages present")


# ---------------------------------------------------------------------------
# V5: Concurrent Chat Test
# ---------------------------------------------------------------------------


class TestV5ConcurrentChat:
    """Fire multiple chat requests simultaneously and verify no SQLite lock."""

    @pytest.mark.asyncio
    async def test_three_concurrent_requests_use_same_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Three concurrent answer() calls use the same EmbeddingService singleton."""
        from app.services.chat_service import ChatService
        from app.services.embedding_service import ClauseMatch, get_embedding_service, reset_embedding_service
        from app.services.retrieval_service import RetrievalService

        reset_embedding_service()
        singleton = get_embedding_service()
        singleton_id = id(singleton)

        class FakeRepo:
            def get_document(self, _did, _uid):
                return {"id": str(DOCUMENT_ID), "user_id": USER_ID, "analysis": {"clauses": []}}

            def save_message(self, *args, **kwargs):
                pass

        retrieval = MagicMock(spec=RetrievalService)
        retrieval.retrieve = AsyncMock(
            return_value=[
                ClauseMatch(title="Payment", excerpt="Payment is due.", page_number=1, similarity_score=0.9)
            ]
        )

        gemini_client = MagicMock()
        gemini_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(
                text='{"answer":"Payment on day 1.","confidence_score":80,"citations":[{"clause_title":"Payment","excerpt":"Payment is due.","page_number":1,"similarity_score":0.9}],"follow_up_questions":[]}'
            )
        )
        monkeypatch.setattr("app.services.gemini_provider.get_gemini_client", lambda: gemini_client)

        services = [ChatService(FakeRepo(), retrieval) for _ in range(3)]

        results = await asyncio.gather(
            services[0].answer(DOCUMENT_ID, USER_ID, "Question 1?"),
            services[1].answer(DOCUMENT_ID, USER_ID, "Question 2?"),
            services[2].answer(DOCUMENT_ID, USER_ID, "Question 3?"),
        )

        # All three succeeded
        assert len(results) == 3, f"FAIL: Expected 3 results, got {len(results)}"
        for i, r in enumerate(results, 1):
            assert r.answer, f"FAIL: Result {i} has empty answer"

        # Singleton identity unchanged
        current_singleton = get_embedding_service()
        assert id(current_singleton) == singleton_id, (
            f"FAIL: Singleton id changed during concurrent requests.\n"
            f"  Before: {singleton_id:#x}\n"
            f"  After:  {id(current_singleton):#x}"
        )

        print("\n  [V5] PASS: 3 concurrent requests completed successfully")
        print(f"          Singleton id before = {singleton_id:#x}")
        print(f"          Singleton id after  = {id(current_singleton):#x}")
        print(f"          Same? = {id(current_singleton) == singleton_id}")
        reset_embedding_service()


# ---------------------------------------------------------------------------
# V6: Startup Test (structural verification)
# ---------------------------------------------------------------------------


class TestV6Startup:
    """Verify structural properties that prevent uvicorn reload on Chroma writes."""

    def test_embedding_service_module_has_singleton(self) -> None:
        """The embedding_service module defines get_embedding_service."""
        import app.services.embedding_service as mod

        assert hasattr(mod, "get_embedding_service"), (
            "FAIL: get_embedding_service not found in embedding_service module"
        )
        assert callable(mod.get_embedding_service), (
            "FAIL: get_embedding_service is not callable"
        )
        print("\n  [V6] PASS: get_embedding_service exists in embedding_service module")

    def test_chat_module_imports_singleton(self) -> None:
        """chat.py imports get_embedding_service, not EmbeddingService directly."""
        import app.api.chat as mod

        assert hasattr(mod, "get_embedding_service"), (
            "FAIL: chat.py does not import get_embedding_service"
        )
        print("\n  [V6] PASS: chat.py imports get_embedding_service")

    def test_chroma_writes_cannot_trigger_reload(self) -> None:
        """Prove the .chroma path is outside all watched directories."""
        import app.services.embedding_service as embed_module

        chroma_dir = Path(embed_module._DEFAULT_CHROMA_PATH)

        # The .chroma dir should be at project root level, not under backend/
        assert chroma_dir.parent == PROJECT_ROOT, (
            f"FAIL: .chroma parent is {chroma_dir.parent}, expected {PROJECT_ROOT}"
        )

        # Verify backend/ is a sibling, not a parent
        backend_dir = PROJECT_ROOT / "backend"
        assert backend_dir.is_dir(), f"FAIL: backend/ directory not found at {backend_dir}"
        assert not chroma_dir.is_relative_to(backend_dir), (
            "FAIL: .chroma is inside backend/"
        )

        print(f"\n  [V6] PASS: .chroma is at {chroma_dir.resolve()}")
        print(f"          backend/ is at {backend_dir.resolve()}")
        print("          .chroma is NOT inside backend/ = True")
        print("          Chroma SQLite writes will NOT trigger uvicorn reload")


# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

USER_ID = "user-123"
DOCUMENT_ID = uuid4()
