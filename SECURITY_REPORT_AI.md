# Security Report — AI / Prompt Injection

## Architecture

- System prompts are loaded **from server files only** (`prompts/legal_analysis.txt`, `prompts/chat_system.txt`) — immutable at request time, never client-supplied.
- User question and retrieved context are separate fields; context is clearly labeled untrusted in the payload: `"Retrieved clauses (untrusted data):"` (`gemini_provider.CHAT_CONTEXT_HEADER`).
- Responses are **schema-constrained** (`response_schema` + `response_mime_type=application/json`, temperature 0.0 for chat) — the model cannot free-form execute anything.
- Automatic function calling is **disabled** on every Gemini config (`AutomaticFunctionCallingConfig(disable=True)`) — uploaded documents can never trigger tool execution.
- No tools/function calling are registered anywhere in the codebase.

## Threat analysis

| Vector | Exposure | Mitigation |
|--------|----------|-----------|
| Instruction override via user question | Chat answers only from retrieved clauses; citations are post-validated against retrieved excerpts (unknown citations dropped, `valid_excerpts` filter) — hallucinated "citations" from injected instructions are discarded | PASS |
| Document prompt injection (malicious PDF) | Document text enters as *data* inside the JSON-labeled untrusted context block, never as system instruction; output is forced into the `LegalAnalysis`/`ChatResponse` pydantic schemas | PASS (residual: content could steer analysis tone — inherent to LLM RAG, no security boundary crossed) |
| Context poisoning | Vector collection is per `sha256(user_id:doc)`; only the owner's analyzed clauses are indexed | PASS |
| System prompt leakage | System instruction never echoed; JSON-schema responses can't include arbitrary prompt text | PASS |
| Hidden Unicode / white-text attacks in uploads | OCR extracts what is literally in the file; hidden text becomes visible data in citations with page numbers — user sees the excerpt verbatim | Documented residual; mitigated by citation transparency |
| HTML comments / markup in documents | Rendered as plain React text | PASS |
| Jailbreak via chat | Schema + temperature 0.0 + grounded-context-only instruction; confidence 0 fallback when no clause matches (`MIN_SIMILARITY=0.35`) | PASS |
| Embedding-model abuse | Query embeddings input-clamped to `EMBEDDING_MAX_INPUT_CHARS` | PASS |

## Citations integrity

`ChatService.answer` filters `result.citations` to excerpts actually retrieved — the citation set shown to the user is provably derived from the user's own document.

**Risk: LOW (residuals are UX-quality, not security boundaries).**
