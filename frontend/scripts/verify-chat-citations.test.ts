// Frontend regression tests for chat citation duplicates (node:test).
//
// Executes the REAL `services/chat` mapper against backend-shaped payloads
// with duplicated citations and asserts:
//   - sendChatMessage / getChatHistory drop exact duplicates
//     (same clause + excerpt + page), keeping the first occurrence
//   - the dashboard chat renderer cannot emit duplicate React keys:
//     keys are `${clauseTitle}-${section}-${index}` (index-suffixed),
//     never the bare human-readable `section` label ("Document").
//
// Run: node --experimental-strip-types --import ./scripts/register-alias.mjs \
//        --test scripts/verify-chat-citations.test.ts
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.dirname(scriptsDir);

(globalThis as unknown as Record<string, unknown>).window = {};
process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
(process.env as Record<string, string | undefined>).NODE_ENV = "test";

const { sendChatMessage, getChatHistory } = await import("@/services/chat");
const { setStubSession } = await import("./supabase-stub.mjs");

const VALID_ID = "123e4567-e89b-12d3-a456-426614174000";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(responder: () => Response): void {
  globalThis.fetch = (async () => responder()) as typeof fetch;
}

/** Mirror of the dashboard citation key: label + section + index. */
function citationKey(c: { clauseTitle: string; section: string }, index: number): string {
  return `${c.clauseTitle}-${c.section}-${index}`;
}

const DUPLICATE_CITATIONS = [
  { clause_title: "Payment", excerpt: "Pay on day one.", page_number: null, similarity_score: 0.9 },
  { clause_title: "Payment", excerpt: "Pay on day one.", page_number: null, similarity_score: 0.9 },
  { clause_title: "Termination", excerpt: "Either party may end it.", page_number: null, similarity_score: 0.8 },
  { clause_title: "Payment", excerpt: "Pay on day one.", page_number: 2, similarity_score: 0.7 },
  { clause_title: "Payment", excerpt: "Pay on day one.", page_number: 2, similarity_score: 0.7 },
];

describe("citation duplicates are removed before rendering", () => {
  beforeEach(() => {
    setStubSession("test-token-abc");
  });

  it("sendChatMessage keeps first occurrences only", async () => {
    stubFetch(() => jsonResponse({ answer: "ok", citations: DUPLICATE_CITATIONS }));
    const message = await sendChatMessage(VALID_ID, "When is payment due?");
    assert.equal(message.citations?.length, 3);
    assert.deepEqual(
      message.citations?.map((c) => `${c.clauseTitle}|${c.section}`),
      ["Payment|Document", "Termination|Document", "Payment|Page 2"],
    );
  });

  it("getChatHistory dedupes citations inside each stored exchange", async () => {
    stubFetch(() =>
      jsonResponse([
        {
          document_id: VALID_ID,
          user_id: "u",
          question: "Q?",
          answer: "A.",
          citations: DUPLICATE_CITATIONS,
          confidence_score: 80,
          timestamp: "2026-01-01T00:00:00Z",
        },
      ]),
    );
    const history = await getChatHistory(VALID_ID);
    const answer = history.find((m) => m.role === "assistant");
    assert.equal(answer?.citations?.length, 3);
  });

  it("rendered citation keys are unique even for same-section citations", async () => {
    stubFetch(() => jsonResponse({ answer: "ok", citations: DUPLICATE_CITATIONS }));
    const message = await sendChatMessage(VALID_ID, "hello");
    const keys = (message.citations ?? []).map(citationKey);
    assert.equal(new Set(keys).size, keys.length, "duplicate React key would warn");
  });
});

describe("static guard: no bare-label React keys in chat rendering", () => {
  function page(): string {
    return readFileSync(path.join(frontendDir, "app/dashboard/[id]/page.tsx"), "utf8");
  }

  it("never uses the human-readable section label as a key", () => {
    assert.ok(!page().includes("key={c.section}"), "bare label key regressed");
  });

  it("citation keys are index-suffixed (stable, unique, deterministic)", () => {
    const content = page();
    assert.ok(
      content.includes("key={`${c.clauseTitle}-${c.section}-${index}`}"),
      "expected label-section-index key",
    );
    assert.ok(!content.includes("Math.random()"), "no random keys");
  });
});
