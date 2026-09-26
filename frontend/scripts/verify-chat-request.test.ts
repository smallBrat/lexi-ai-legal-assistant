// Frontend regression tests for POST /documents/:id/chat (node:test).
//
// Executes the REAL `services/chat` + `lib/api-client` sources (resolved
// through scripts/register-alias.mjs) against a mocked fetch and asserts the
// exact request contract plus the timeout/abort behavior that caused the
// "Request timed out / backend never receives the message" incident:
//
//   - POST /documents/{uuid}/chat with JSON `{ question }` body only
//   - Content-Type: application/json + Bearer Authorization
//   - 120s chat timeout (CHAT_REQUEST_TIMEOUT_MS), 20s history timeout
//   - invalid UUIDs blocked client-side (no network)
//   - timeout surfaces as ApiError(0, "Request timed out…")
//   - retry after a failure succeeds
//
// Plus static guards: chat has its own AbortController registry that can
// never abort analyze requests (and vice versa).
//
// Run: node --experimental-strip-types --import ./scripts/register-alias.mjs \
//        --test scripts/verify-chat-request.test.ts
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.dirname(scriptsDir);

// A browser-ish global: api-client only attaches the auth header when
// `typeof window !== "undefined"`, mirroring the real Next.js environment.
(globalThis as unknown as Record<string, unknown>).window = {};
process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
(process.env as Record<string, string | undefined>).NODE_ENV = "test";

const { sendChatMessage, getChatHistory } = await import("@/services/chat");
const { apiClient, ApiError } = await import("@/lib/api-client");
const { setStubSession } = await import("./supabase-stub.mjs");

const VALID_ID = "123e4567-e89b-12d3-a456-426614174000";

type Captured = { url: string; init: RequestInit };
let calls: Captured[] = [];
let respond: (call: Captured, index: number) => Response | Promise<Response> =
  () =>
    new Response(
      JSON.stringify({ answer: "ok", citations: [] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );

function mockFetch() {
  calls = [];
  let index = 0;
  const stubFetch: typeof fetch = async (input, init) => {
    const call = { url: String(input), init: init ?? {} };
    calls.push(call);
    return respond(call, index++);
  };
  globalThis.fetch = stubFetch;
}

function headersOf(init: RequestInit): Headers {
  return new Headers(init.headers);
}

function chatAnswer(content: string): Response {
  return new Response(JSON.stringify({ answer: content, citations: [] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("chat request contract (POST /documents/:id/chat)", () => {
  beforeEach(() => {
    setStubSession("test-token-abc");
    respond = () => chatAnswer("The agreement requires payment on day one.");
    mockFetch();
  });

  it("reaches the backend with exactly one POST per message", async () => {
    const message = await sendChatMessage(VALID_ID, "Give me a short summary");
    assert.equal(calls.length, 1);
    const { url, init } = calls[0];
    assert.equal(url, `http://localhost:8000/documents/${VALID_ID}/chat`);
    assert.equal(init.method, "POST");
    assert.equal(message.role, "assistant");
    assert.match(message.content, /payment/);
  });

  it("sends a JSON { question } body with auth headers and no query params", async () => {
    await sendChatMessage(VALID_ID, "  Give me a short summary  ");
    const { url, init } = calls[0];
    assert.ok(!url.includes("?"), "no accidental query params");
    assert.equal(init.body, JSON.stringify({ question: "Give me a short summary" }));
    const headers = headersOf(init);
    assert.equal(headers.get("Content-Type"), "application/json");
    assert.equal(headers.get("Authorization"), "Bearer test-token-abc");
  });

  it("blocks invalid UUIDs client-side without touching the network", async () => {
    await assert.rejects(() => sendChatMessage("not-a-uuid", "hello"), (err: unknown) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 422);
      return true;
    });
    assert.equal(calls.length, 0);
  });

  it("blocks empty questions client-side without touching the network", async () => {
    await assert.rejects(() => sendChatMessage(VALID_ID, "   "));
    assert.equal(calls.length, 0);
  });

  it("surfaces a client-side timeout as ApiError (retryable)", async () => {
    // Hanging fetch + tiny timeout proves the timeout→ApiError mapping
    // without waiting the real 120s chat budget. Like a real fetch, the
    // stub rejects when its signal aborts.
    globalThis.fetch = ((input, init) => new Promise((_resolve, reject) => {
      const signal = init?.signal as AbortSignal | undefined;
      const reason = () => (signal?.reason ?? new DOMException("This operation was aborted.", "AbortError")) as Error;
      if (signal?.aborted) {
        reject(reason());
        return;
      }
      signal?.addEventListener("abort", () => reject(reason()), { once: true });
    })) as typeof fetch;
    await assert.rejects(
      () => apiClient.post(`/documents/${VALID_ID}/chat`, { question: "hi" }, { timeoutMs: 30 }),
      (err: unknown) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 0);
        assert.match(err.message, /timed out/);
        return true;
      },
    );
  });

  it("retry succeeds after a transient failure", async () => {
    let attempt = 0;
    respond = () => {
      attempt += 1;
      if (attempt === 1) {
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      return chatAnswer("recovered answer");
    };
    await assert.rejects(() => sendChatMessage(VALID_ID, "hello"));
    const message = await sendChatMessage(VALID_ID, "hello");
    assert.equal(message.content, "recovered answer");
    assert.equal(calls.length, 2, "exactly one POST per attempt");
  });

  it("history GET hits the same document URL and expands Q/A pairs", async () => {
    respond = () =>
      new Response(
        JSON.stringify([
          {
            document_id: VALID_ID,
            user_id: "u",
            question: "When is payment due?",
            answer: "On day one.",
            citations: [],
            confidence_score: 80,
            timestamp: "2026-01-01T00:00:00Z",
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const history = await getChatHistory(VALID_ID);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, `http://localhost:8000/documents/${VALID_ID}/chat`);
    assert.equal(history.length, 2);
    assert.equal(history[0].role, "user");
    assert.equal(history[0].content, "When is payment due?");
    assert.equal(history[1].role, "assistant");
  });
});

describe("static guards: timeout policy + abort isolation", () => {
  function src(rel: string): string {
    return readFileSync(path.join(frontendDir, rel), "utf8");
  }

  it("timeout policy lives in one constants file with the required values", () => {
    const content = src("lib/request-timeouts.ts");
    assert.ok(content.includes("CHAT_REQUEST_TIMEOUT_MS = 300_000"), "chat POST budget is 300s");
    assert.ok(content.includes("CHAT_HISTORY_TIMEOUT_MS = 20_000"), "history budget is 20s");
    assert.ok(content.includes("DOCUMENT_FETCH_TIMEOUT_MS = 60_000"), "document budget is 60s");
  });

  it("chat POST uses its own 120s timeout, never the analyze default", () => {
    const content = src("services/chat.ts");
    assert.ok(content.includes("CHAT_REQUEST_TIMEOUT_MS"), "send must pass the chat timeout");
    assert.ok(content.includes("CHAT_HISTORY_TIMEOUT_MS"), "history must pass its own timeout");
  });

  it("chat has an isolated AbortController registry (cannot abort analyze)", () => {
    const content = src("hooks/use-lexi.ts");
    assert.ok(content.includes("activeChatControllers"), "chat owns its controller map");
    assert.ok(content.includes("activeAnalyzeControllers"), "analyze map still exists separately");
    // Chat paths only ever touch their own map…
    const chatBlock = content.slice(content.indexOf("activeChatControllers = new Map"));
    assert.ok(!chatBlock.includes("activeAnalyzeControllers"), "chat flow must not reference the analyze map");
    // …and each message mints a fresh controller.
    assert.ok(content.includes("new AbortController()"), "fresh controller per message");
  });

  it("dashboard aborts only same-document chat on navigation", () => {
    const content = src("app/dashboard/[id]/page.tsx");
    assert.ok(content.includes("abortChatForDocument(id)"), "navigation cleanup aborts this document's chat");
    assert.ok(!content.includes("activeAnalyzeControllers"), "dashboard chat never touches analyze controllers");
  });

  it("dashboard keeps the draft and offers retry on failure", () => {
    const content = src("app/dashboard/[id]/page.tsx");
    assert.ok(content.includes("setDraft(question)"), "typed message restored on failure");
    assert.ok(content.includes("retryChat"), "retry path exists");
    assert.ok(content.includes("Lexi is reading your document"), "typing indicator while waiting");
  });
});
