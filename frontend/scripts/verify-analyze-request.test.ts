// Frontend regression test for POST /analyze/{document_id} (node:test).
//
// Executes the REAL `services/analysis` + `lib/api-client` sources (resolved
// through scripts/register-alias.mjs) against a mocked fetch and asserts the
// exact request contract that eliminates the recurring 422:
//
//   - no request body (body key absent, no Content-Type header)
//   - correct query (?force=true only when force, otherwise none)
//   - correct Authorization header (Bearer, value from the session)
//
// Plus static guards: no hardcoded demo ids anywhere in the analyze flow.
//
// Run: node --experimental-strip-types --import ./scripts/register-alias.mjs \
//        --test scripts/verify-analyze-request.test.ts
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

const { getAnalysis, isValidDocumentId } = await import("@/services/analysis");
const { ApiError } = await import("@/lib/api-client");
const { setStubSession } = await import("./supabase-stub.mjs");

const VALID_ID = "123e4567-e89b-12d3-a456-426614174000";

type Captured = { url: string; init: RequestInit };
let calls: Captured[] = [];

function mockFetch() {
  calls = [];
  const stubFetch: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init: init ?? {} });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  globalThis.fetch = stubFetch;
}

function headersOf(init: RequestInit): Headers {
  return new Headers(init.headers);
}

describe("analyze request contract (POST /analyze/:id)", () => {
  beforeEach(() => {
    setStubSession("test-token-abc");
    mockFetch();
  });

  it("accepts real UUIDs and rejects demo slugs", () => {
    assert.equal(isValidDocumentId(VALID_ID), true);
    assert.equal(isValidDocumentId("msa-v2"), false);
    assert.equal(isValidDocumentId("msa-v1"), false);
    assert.equal(isValidDocumentId(""), false);
    assert.equal(isValidDocumentId("undefined"), false);
    assert.equal(isValidDocumentId("not-a-uuid"), false);
  });

  it("sends POST with no body, no query, and auth header by default", async () => {
    await getAnalysis(VALID_ID);
    assert.equal(calls.length, 1);
    const { url, init } = calls[0];
    assert.equal(url, `http://localhost:8000/analyze/${VALID_ID}`);
    assert.equal(init.method, "POST");
    assert.ok(!("body" in init) || init.body === undefined, "no body bytes may be sent");
    const headers = headersOf(init);
    assert.equal(headers.get("Content-Type"), null);
    assert.equal(headers.get("Authorization"), "Bearer test-token-abc");
  });

  it("appends ?force=true only when force is set (still no body)", async () => {
    await getAnalysis(VALID_ID, true);
    assert.equal(calls.length, 1);
    const { url, init } = calls[0];
    assert.equal(url, `http://localhost:8000/analyze/${VALID_ID}?force=true`);
    assert.ok(!("body" in init) || init.body === undefined);
    assert.equal(headersOf(init).get("Content-Type"), null);
  });

  it("never emits ?force=false (server default covers it)", async () => {
    await getAnalysis(VALID_ID, false);
    assert.equal(calls[0].url, `http://localhost:8000/analyze/${VALID_ID}`);
  });

  it("refuses demo/non-UUID ids client-side without touching the network", async () => {
    await assert.rejects(() => getAnalysis("msa-v2"), (err: unknown) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 422);
      return true;
    });
    assert.equal(calls.length, 0, "no doomed POST /analyze/msa-v2 may leave the client");
  });
});

describe("static guards: no stray analyze triggers", () => {
  function src(rel: string): string {
    return readFileSync(path.join(frontendDir, rel), "utf8");
  }

  it("no hardcoded demo document ids in the analyze flow", () => {
    // Quoted occurrences only: comments may document the removed footgun,
    // but no string literal may ever route a request at a demo slug again.
    const scanned = [
      "app/report/page.tsx",
      "app/processing/page.tsx",
      "app/compare/results/page.tsx",
      "app/dashboard/[id]/page.tsx",
      "components/layout/dashboard-shell.tsx",
      "services/analysis.ts",
      "hooks/use-lexi.ts",
      "lib/api-client.ts",
    ];
    for (const rel of scanned) {
      const content = src(rel);
      assert.ok(!content.includes('"msa-v'), `${rel} must not reference a demo id literal`);
      assert.ok(!content.includes("'msa-v"), `${rel} must not reference a demo id literal`);
    }
  });

  it("api-client only declares JSON when a body is actually sent", () => {
    const content = src("lib/api-client.ts");
    assert.ok(
      content.includes("init.body !== undefined"),
      "Content-Type must be conditional on a real body",
    );
  });

  it("analysis service passes undefined (not {}) as the POST body", () => {
    const content = src("services/analysis.ts");
    assert.ok(content.includes("undefined"), "analyze must send no body");
    assert.ok(!content.includes("JSON.stringify(undefined ?? {})"), "old {} fallback must stay gone");
  });
});
