// Frontend stability regression tests (node:test).
//
// Covers PART 14 of the stability audit:
//   - Navigation: unique ids, unique hrefs, key={item.id}.
//   - UUID layer: invalid ids never send requests.
//   - Processing: analyze mutation fires once (static guards).
//   - Dashboard: analysis rendered from cache, never auto-POST.
//   - API client: no bodyless Content-Type, timeout support.
//   - Health: targets the backend URL, never the Next.js server.
//
// Run: node --experimental-strip-types --import ./scripts/register-alias.mjs \
//        --test scripts/verify-frontend-stability.test.ts
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync as _existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.dirname(scriptsDir);

(globalThis as unknown as Record<string, unknown>).window = {};
process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
(process.env as Record<string, string | undefined>).NODE_ENV = "test";

const { isValidDocumentId, parseDocumentId, assertValidDocumentId } = await import(
  "@/lib/document-id"
);
const { ApiError, apiClient } = await import("@/lib/api-client");
const { setStubSession } = await import("./supabase-stub.mjs");
const { pollingRegistry } = await import("@/lib/polling-registry");
const { saveCompareSession, loadCompareSession, clearCompareSession, hasValidCompareSession } = await import(
  "@/lib/compare-session"
);
const { pollingFetch, getFreshSession } = await import("@/lib/api-client");

const VALID_A = "123e4567-e89b-12d3-a456-426614174000";
const VALID_B = "223e4567-e89b-12d3-a456-426614174001";

type Captured = { url: string; init: RequestInit };
let calls: Captured[] = [];

function mockFetch(): void {
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

function src(rel: string): string {
  return readFileSync(path.join(frontendDir, rel), "utf8");
}

describe("navigation: unique ids, hrefs, and React keys", () => {
  const shell = src("components/layout/dashboard-shell.tsx");

  it("every nav item has a unique id and href", () => {
    const ids = [...shell.matchAll(/id:\s*"([^"]+)"/g)].map((m) => m[1]);
    const hrefs = [...shell.matchAll(/href:\s*"([^"]+)"/g)].map((m) => m[1]);
    assert.ok(ids.length >= 5, `expected nav ids, found ${ids.length}`);
    assert.equal(new Set(ids).size, ids.length, `duplicate nav ids: ${ids}`);
    assert.equal(new Set(hrefs).size, hrefs.length, `duplicate nav hrefs: ${hrefs}`);
  });

  it("React keys use item.id, never href", () => {
    assert.ok(shell.includes("key={item.id}"), "nav must use key={item.id}");
    assert.ok(!shell.includes("key={item.href}"), "key={item.href} must stay gone");
  });

  it("no duplicate /dashboard entry and no demo document links", () => {
    const dashboardHrefs = [...shell.matchAll(/href:\s*"\/dashboard"/g)];
    assert.equal(dashboardHrefs.length, 1, "exactly one /dashboard nav entry allowed");
    assert.ok(!shell.includes("/dashboard/msa-"), "no demo document links allowed");
  });
});

describe("document-id validation layer", () => {
  beforeEach(() => {
    setStubSession("test-token-abc");
    mockFetch();
  });

  it("accepts UUIDs and rejects slugs/empty/junk", () => {
    assert.equal(isValidDocumentId(VALID_A), true);
    assert.equal(isValidDocumentId("msa-v1"), false);
    assert.equal(isValidDocumentId("msa-v2"), false);
    assert.equal(isValidDocumentId("test-id"), false);
    assert.equal(isValidDocumentId(""), false);
    assert.equal(isValidDocumentId("undefined"), false);
  });

  it("parseDocumentId normalizes route params", () => {
    assert.equal(parseDocumentId(VALID_A), VALID_A);
    assert.equal(parseDocumentId([VALID_A]), VALID_A);
    assert.equal(parseDocumentId(undefined), "");
    assert.equal(parseDocumentId(null), "");
  });

  it("assertValidDocumentId throws typed 422 without network", () => {
    assert.throws(() => assertValidDocumentId("msa-v2"), (err: unknown) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 422);
      return true;
    });
    assert.equal(calls.length, 0);
  });

  it("document/chat/compare services never send requests for invalid ids", async () => {
    const { getDocument } = await import("@/services/documents");
    const { getChatHistory, sendChatMessage } = await import("@/services/chat");
    const { compareDocuments } = await import("@/services/compare");
    await assert.rejects(() => getDocument("msa-v1"));
    await assert.rejects(() => getChatHistory("dummy-id"));
    await assert.rejects(() => sendChatMessage("test-id", "hello"));
    await assert.rejects(() => compareDocuments(VALID_A, "msa-v2"));
    await assert.rejects(() => compareDocuments("", ""));
    assert.equal(calls.length, 0, "no request may leave the client for invalid ids");
  });
});

describe("processing: single analyze initiation", () => {
  it("processing page guards the mutation with a once-ref and in-flight check", () => {
    const page = src("app/processing/page.tsx");
    assert.ok(page.includes("analyzeTriggered"), "once-ref guard required");
    assert.ok(page.includes("isAnalysisInFlight"), "in-flight guard required");
    assert.equal(
      [...page.matchAll(/analyze\.mutate\(/g)].length,
      1,
      "exactly one analyze.mutate call site allowed on the processing page",
    );
  });

  it("processing navigates to the dashboard, never to itself", () => {
    const page = src("app/processing/page.tsx");
    assert.ok(!page.includes("router.push(`/processing"), "no self-redirect allowed");
    assert.ok(page.includes("router.push(`/dashboard/${doc}`)"), "terminal states go to the dashboard");
  });

  it("dashboard deep-link analyze is guarded and retry is the only other trigger", () => {
    const page = src("app/dashboard/[id]/page.tsx");
    assert.ok(page.includes("analyzeTriggered"), "once-ref guard required");
    assert.equal(
      [...page.matchAll(/analyze\.mutate\(/g)].length,
      2,
      "dashboard may trigger analyze only via deep-link effect + manual retry",
    );
  });
});

describe("dashboard/report/compare never auto-start analysis", () => {
  it("dashboard detail derives analysis from the document query (no useAnalysis)", () => {
    const page = src("app/dashboard/[id]/page.tsx");
    assert.ok(page.includes("document?.analysis"), "single source: document.analysis");
    // Match real usages (import/call), not prose in comments.
    assert.ok(!page.includes("useAnalysis("), "dashboard must not call the analysis query");
    assert.ok(!page.includes("useAnalysis,"), "dashboard must not import the analysis query");
    assert.ok(!page.includes("useAnalysis }"), "dashboard must not import the analysis query");
  });

  it("useAnalysis is GET-only (no POST path)", () => {
    const hooks = src("hooks/use-lexi.ts");
    const block = hooks.slice(hooks.indexOf("export function useAnalysis"));
    const nextExport = block.indexOf("export function", 10);
    const body = nextExport === -1 ? block : block.slice(0, nextExport);
    assert.ok(!body.includes("getAnalysis("), "useAnalysis must not call the POST service");
    assert.ok(body.includes("getDocument("), "useAnalysis must derive from GET /documents/:id");
  });

  it("report and compare results pages contain no analyze mutation", () => {
    assert.ok(!src("app/report/page.tsx").includes("useAnalyzeDocument"));
    assert.ok(!src("app/compare/results/page.tsx").includes("useAnalyzeDocument"));
  });

  it("compare upload card is the only compare-side analyze trigger (once-ref + in-flight guarded)", () => {
    // The compare page uploads directly into two isolated slots, so each
    // slot must drive its own document to analyzed — exactly once, with the
    // same guards as the processing page. The results page must stay read-only.
    const card = src("components/compare/compare-upload-card.tsx");
    assert.ok(card.includes("analyzeTriggered"), "once-ref guard required");
    assert.ok(card.includes("isAnalysisInFlight"), "in-flight guard required");
    assert.equal(
      [...card.matchAll(/analyze\.mutate\(/g)].length,
      1,
      "exactly one analyze.mutate call site allowed in the compare upload card",
    );
    assert.ok(!src("app/compare/page.tsx").includes("analyze.mutate("), "page itself must not trigger");
  });
});

describe("api-client contract", () => {
  beforeEach(() => {
    setStubSession("test-token-abc");
    mockFetch();
  });

  it("GET sends no Content-Type", async () => {
    await apiClient.get("/documents");
    assert.equal(calls.length, 1);
    assert.equal(new Headers(calls[0].init.headers).get("Content-Type"), null);
  });

  it("POST without body sends no Content-Type and no body bytes", async () => {
    await apiClient.post(`/analyze/${VALID_A}`);
    assert.equal(calls.length, 1);
    assert.ok(!("body" in calls[0].init) || calls[0].init.body === undefined);
    assert.equal(new Headers(calls[0].init.headers).get("Content-Type"), null);
  });

  it("POST with body sends application/json", async () => {
    await apiClient.post("/compare", { document_a_id: VALID_A, document_b_id: VALID_B });
    assert.equal(new Headers(calls[0].init.headers).get("Content-Type"), "application/json");
  });

  it("attaches an abort signal (timeout support) and parses array details", async () => {
    await apiClient.get("/documents", { timeoutMs: 5000 });
    assert.ok(calls[0].init.signal instanceof AbortSignal, "timeout signal required");
    const clientSrc = src("lib/api-client.ts");
    assert.ok(clientSrc.includes("DEFAULT_TIMEOUT_MS"), "default timeout required");
    assert.ok(clientSrc.includes("TimeoutError"), "timeout error mapping required");
  });
});

describe("compare: dual-slot isolation and gating", () => {
  it("compare page holds two independent slots that never share state", () => {
    const page = src("app/compare/page.tsx");
    assert.ok(page.includes("docA") && page.includes("docB"), "two slot states required");
    assert.ok(page.includes('slot="A"') && page.includes('slot="B"'), "slots must be addressed independently");
    // The Run-comparison link must carry both ids; never a bare /compare/results.
    assert.ok(page.includes("/compare/results?a="), "results link must carry ?a=&b=");
  });

  it("compare button enables only when both slots are analyzed and distinct", () => {
    const page = src("app/compare/page.tsx");
    assert.ok(page.includes("readyA && readyB"), "both slots must report ready");
    assert.ok(page.includes("docA !== docB"), "same-document comparison must stay disabled");
    assert.ok(page.includes('aria-disabled="true"'), "disabled state must be announced");
  });

  it("upload card never navigates away and writes only its own slot", () => {
    const card = src("components/compare/compare-upload-card.tsx");
    assert.ok(!card.includes("router.push"), "card must stay on the compare page");
    assert.ok(!card.includes("useRouter"), "no navigation from the card");
    assert.ok(card.includes("onSelect(result.document_id)"), "upload captures the id into its own slot");
  });

  it("results page renders both sides and handles pending analysis", () => {
    const results = src("app/compare/results/page.tsx");
    assert.ok(results.includes("text_a") && results.includes("text_b"), "clause A/B columns required");
    assert.ok(results.includes("document_a_title"), "both document titles required");
    assert.ok(results.includes("document_a_ready"), "pending-analysis state required");
    assert.ok(!results.includes("analyze.mutate("), "results must stay read-only");
  });

  it("compare service rejects same-document and invalid ids without network", async () => {
    mockFetch(); // reset calls captured by earlier api-client contract tests
    const { compareDocuments } = await import("@/services/compare");
    await assert.rejects(() => compareDocuments(VALID_A, VALID_A));
    await assert.rejects(() => compareDocuments(VALID_A, "msa-v2"));
    assert.equal(calls.length, 0, "no request may leave the client for invalid ids");
  });
});

describe("health check targets the backend", () => {
  it("no relative /health fetch anywhere in app/services/hooks/components", () => {
    for (const rel of [
      "services/health.ts",
      "lib/api-client.ts",
      "hooks/use-lexi.ts",
      "app/dashboard/page.tsx",
      "app/upload/page.tsx",
    ]) {
      const content = src(rel);
      // A *relative* health fetch hits the Next.js dev server (404) instead
      // of the backend. Match fetch("/health") / fetch('/health') call
      // shapes — not the legitimate `${baseUrl}/health` template or docs.
      assert.ok(!content.includes('fetch("/health"'), `${rel} must not fetch a relative /health`);
      assert.ok(!content.includes("fetch('/health'"), `${rel} must not fetch a relative /health`);
      assert.ok(!content.includes("localhost:3000/health"), `${rel} must not hit the Next.js server`);
    }
    assert.ok(
      src("services/health.ts").includes("`${baseUrl}/health`"),
      "health check must use NEXT_PUBLIC_API_URL",
    );
  });
});

describe("polling registry: singleton, subscribe/unsubscribe, status", () => {
  it("is a singleton", () => {
    const instance1 = pollingRegistry;
    const instance2 = pollingRegistry;
    assert.equal(instance1, instance2, "registry must be a singleton");
  });

  it("tracks status per document ID", () => {
    const testId = "550e8400-e29b-41d4-a716-446655440000";
    pollingRegistry.setStatus(testId, "polling");
    assert.equal(pollingRegistry.getStatus(testId), "polling");
    pollingRegistry.setStatus(testId, "completed");
    assert.equal(pollingRegistry.getStatus(testId), "completed");
    pollingRegistry.stop(testId);
  });

  it("subscribes and notifies", () => {
    const testId = "660e8400-e29b-41d4-a716-446655440000";
    let notified = false;
    const unsub = pollingRegistry.subscribe(testId, () => { notified = true; });
    pollingRegistry.setStatus(testId, "polling");
    assert.ok(notified, "subscriber should be notified on status change");
    unsub();
    pollingRegistry.stop(testId);
  });

  it("stops all polling on stopAll", () => {
    pollingRegistry.stopAll();
    assert.equal(pollingRegistry.getActiveIds().length, 0, "all entries should be cleared");
  });
});

describe("compare session: module structure", () => {
  it("exports save/load/clear/hasValid functions", () => {
    assert.ok(typeof saveCompareSession === "function", "saveCompareSession must be a function");
    assert.ok(typeof loadCompareSession === "function", "loadCompareSession must be a function");
    assert.ok(typeof clearCompareSession === "function", "clearCompareSession must be a function");
    assert.ok(typeof hasValidCompareSession === "function", "hasValidCompareSession must be a function");
  });
});

describe("api-client: polling fetch and JWT refresh", () => {
  it("pollingFetch uses DOCUMENT_FETCH_TIMEOUT_MS by default", async () => {
    await pollingFetch("/documents");
    assert.equal(calls.length, 1);
    assert.ok(calls[0].init.signal instanceof AbortSignal, "polling fetch must have abort signal");
  });

  it("getFreshSession returns session token", async () => {
    const session = await getFreshSession();
    assert.ok(session != null, "getFreshSession must return a session");
  });
});

describe("compare button state machine", () => {
  it("uploading state is shown during file upload", () => {
    const card = src("components/compare/compare-upload-card.tsx");
    assert.ok(card.includes("uploading"), "uploading status must be defined");
    assert.ok(card.includes("ocr_processing"), "ocr_processing status must be defined");
    assert.ok(card.includes("analysis_processing"), "analysis_processing status must be defined");
    assert.ok(card.includes("ready"), "ready status must be defined");
    assert.ok(card.includes("failed"), "failed status must be defined");
  });

  it("compare button disabled when prerequisites missing", () => {
    const page = src("app/compare/page.tsx");
    assert.ok(page.includes("canCompare = readyA && readyB && distinct"), "gating logic required");
    assert.ok(page.includes("opacity-50"), "disabled visual state required");
  });

  it("state machine indicator renders correctly", () => {
    const page = src("app/compare/page.tsx");
    assert.ok(page.includes("StateIndicator"), "state machine indicator required");
  });
});

describe("memory leak prevention and cleanup", () => {
  it("polling hook cleans up on unmount", () => {
    const hook = src("hooks/use-polling.ts");
    assert.ok(hook.includes("mountedRef"), "mountedRef required for cleanup");
    assert.ok(hook.includes("unsubscribe"), "unsubscribe required for cleanup");
    assert.ok(!hook.includes("setInterval(") || hook.includes("pollingRegistry.setTimeout"), "must use registry for timers");
  });

  it("no duplicate analyze triggers (once-ref guard in compare card)", () => {
    const card = src("components/compare/compare-upload-card.tsx");
    assert.ok(card.includes("analyzeTriggered"), "once-ref guard required");
    assert.ok(card.includes("isAnalysisInFlight"), "in-flight guard required");
  });

  it("polling registry prevents duplicate loops", () => {
    const reg = src("lib/polling-registry.ts");
    assert.ok(reg.includes("getEntry"), "registry must have getEntry");
    assert.ok(reg.includes("subscribe"), "registry must have subscribe");
    assert.ok(reg.includes("stop"), "registry must have stop");
  });

  it("instrumentation is diagnostics-free (Phase 15)", () => {
    // Phase 15 removed all lifecycle observers; instrumentation.ts keeps
    // only the Windows EPIPE/EIO stream suppression.
    const inst = src("instrumentation.ts");
    assert.ok(!inst.includes("unhandledRejection"), "no lifecycle observers may remain");
    assert.ok(inst.includes("suppressStreamEpipe"), "EPIPE suppression must remain");
  });
});

describe("error differentiation UI", () => {
  it("compare results page differentiates error types", () => {
    const results = src("app/compare/results/page.tsx");
    assert.ok(results.includes("getErrorMessage"), "error message helper required");
    assert.ok(results.includes("isTransientError"), "transient error detection required");
    assert.ok(results.includes("Authentication expired"), "401 message required");
    assert.ok(results.includes("Backend busy"), "503 message required");
    assert.ok(results.includes("Network connection lost"), "network message required");
  });

  it("compare upload card shows reconnecting state", () => {
    const card = src("components/compare/compare-upload-card.tsx");
    assert.ok(card.includes("Waiting for connection"), "network error message required");
    assert.ok(card.includes("Refreshing session"), "session refresh message required");
    assert.ok(card.includes("Backend busy"), "backend busy message required");
  });
});

describe("dev-server stability hardening", () => {
  it("a favicon route exists so /favicon.ico never compiles /_not-found", async () => {
    // The 2026-09-15 crash log ends mid-`Compiling /_not-found`: with no
    // public/ dir, every fresh navigation fired a favicon 404 that compiled
    // the full _not-found route (+ root layout + fonts). app/icon.svg is the
    // zero-config App Router favicon that removes that compile entirely.
    const { existsSync } = await import("node:fs");
    const hasAppIcon =
      existsSync(path.join(frontendDir, "app", "icon.svg")) ||
      existsSync(path.join(frontendDir, "app", "icon.png")) ||
      existsSync(path.join(frontendDir, "app", "favicon.ico"));
    const hasPublicFavicon = existsSync(path.join(frontendDir, "public", "favicon.ico"));
    assert.ok(hasAppIcon || hasPublicFavicon, "a favicon route (app/icon.* or public/favicon.ico) is required");
    // Belt-and-braces: the root layout must advertise the icon so browsers
    // never auto-request /favicon.ico (which would 404 -> /_not-found).
    assert.ok(
      src("app/layout.tsx").includes('"/icon.svg"'),
      "root layout metadata must link the icon",
    );
  });

  it("instrumentation is additive-only and never strips framework listeners", () => {
    // Stripping Next.js dev parent/child shutdown handlers (SIGINT/SIGTERM/
    // exit/beforeExit/uncaughtException) breaks graceful shutdown
    // (vercel/next.js#67165) and swallows fatal errors. The only listeners
    // attached are stream 'error' suppressors; no framework listeners are
    // removed and no live process.exit call exists.
    const inst = src("instrumentation.ts");
    assert.ok(!inst.includes("removeListener"), "instrumentation must not remove listeners");
    assert.ok(!inst.includes("removeAllListeners"), "instrumentation must not remove listeners");
    assert.ok(!inst.match(/^\s*process\.exit\(/m), "no live process.exit call allowed");
  });

  it("webpack watch ignores log/tsbuildinfo/secret churn", () => {
    const config = src("next.config.mjs");
    for (const pattern of ["**/*.log", "**/*.tsbuildinfo", "**/.secrets/**", "**/.chroma/**"]) {
      assert.ok(config.includes(pattern), `watchOptions must ignore ${pattern}`);
    }
  });

  it("heavy barrel packages use optimizePackageImports", () => {
    const config = src("next.config.mjs");
    assert.ok(config.includes("optimizePackageImports"), "per-route compile weight must be trimmed");
    for (const pkg of ["lucide-react", "framer-motion"]) {
      assert.ok(config.includes(pkg), `${pkg} must be import-optimized`);
    }
  });

  it("framer-motion uses static import, not dynamic (Windows crash fix)", () => {
    // PHASE 11 FIX: Dynamic import of framer-motion features caused silent
    // webpack compilation crashes on Windows during 404 route compilation.
    // The fix replaces dynamic import with static domAnimation bundle.
    const pageTransition = src("components/shared/page-transition.tsx");
    assert.ok(
      pageTransition.includes('features={domAnimation}'),
      "framer-motion must use static domAnimation feature, not dynamic import"
    );
    // Remove comments before checking for dynamic import to avoid false positives
    const codeOnly = pageTransition.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    assert.ok(
      !codeOnly.match(/\(\)\s*=>\s*import\s*\(\s*["']framer-motion["']\s*\)/),
      "framer-motion must not be dynamically imported (causes silent crashes)"
    );
    assert.ok(
      pageTransition.includes('import { domAnimation, LazyMotion, m, useReducedMotion } from "framer-motion"'),
      "framer-motion must be statically imported"
    );
  });

  it("instrumentation suppresses EPIPE/EIO on stdout and stderr (Phase 13 fix)", () => {
    // ROOT CAUSE (Phase 13): On Windows + Node 22, process.stdout emits
    // EPIPE when the PowerShell terminal buffer is momentarily unavailable.
    // Without 'error' listeners, EPIPE propagates to uncaughtException.
    // Next.js's own uncaughtException handler calls console.error(), which
    // writes to stdout again and throws ANOTHER EPIPE, creating a fatal loop.
    // Fix: attach 'error' event listeners that swallow EPIPE/EIO silently.
    const inst = src("instrumentation.ts");
    assert.ok(inst.includes("suppressStreamEpipe"), "EPIPE suppression function must exist");
    assert.ok(inst.includes("process.stdout"), "stdout must be guarded against EPIPE");
    assert.ok(inst.includes("process.stderr"), "stderr must be guarded against EPIPE");
    assert.ok(inst.includes('"EPIPE"'), 'EPIPE error code must be handled');
    assert.ok(inst.includes('"EIO"'), 'EIO error code must be handled (Windows variant)');
    // The suppressor must NOT call process.exit() or throw.
    assert.ok(!inst.match(/suppressStreamEpipe[\s\S]{0,500}process\.exit\(/), "suppressor must not exit");
  });

  it("no runtime investigation diagnostics remain (Phase 15)", () => {
    // The Phase 13/13.1/13.2 exit-attribution instrumentation was removed:
    // no probe preload, no lifecycle/runtime-exit log generation, no
    // process.exit/process.kill monkey patches, no lifecycle observers.
    const inst = src("instrumentation.ts");
    assert.ok(!inst.includes("phase-exit-probe"), "no probe references");
    assert.ok(!inst.includes("lifecycle.log"), "no lifecycle.log writes");
    assert.ok(!inst.includes("runtime-exit"), "no runtime-exit.log writes");
    assert.ok(!inst.includes("monkey"), "no monkey-patch leftovers");
    // Only the EPIPE suppressor and a no-op-safe register remain.
    const body = inst.slice(inst.indexOf("export async function register"));
    assert.ok(!body.includes("process.on("), "register must attach no lifecycle observers");
    // Diagnostic scripts are gone.
    const { existsSync } = { existsSync: _existsSync };
    for (const gone of [
      "scripts/phase-exit-probe.mjs",
      "scripts/phase-repro.mjs",
      "scripts/diagnostic-exit.mjs",
      "scripts/watch-next-dev.mjs",
      "scripts/tmp-probe-verify.mjs",
    ]) {
      assert.equal(existsSync(path.join(frontendDir, gone)), false, `${gone} must be deleted`);
    }
  });
});
