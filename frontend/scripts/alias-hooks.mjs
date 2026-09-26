// Resolve-hook file for the analyze-request contract test.
//
// Maps the `@/` path alias used by the Next.js frontend to real files so the
// test can import the ACTUAL `services/analysis` + `lib/api-client` sources
// under plain node (with --experimental-strip-types). The Supabase module is
// replaced with a stub so no network or browser globals are required.
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const stubUrl = pathToFileURL(path.join(frontendDir, "scripts", "supabase-stub.mjs")).href;

const EXTENSIONS = [".ts", ".tsx", ".mjs", ".js"];

function probe(base) {
  for (const ext of EXTENSIONS) {
    const candidate = base + ext;
    if (existsSync(candidate)) return pathToFileURL(candidate).href;
  }
  for (const index of ["/index.ts", "/index.tsx", "/index.mjs", "/index.js"]) {
    const candidate = base + index;
    if (existsSync(candidate)) return pathToFileURL(candidate).href;
  }
  return null;
}

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@/lib/supabase") {
    return { url: stubUrl, shortCircuit: true };
  }
  if (specifier.startsWith("@/")) {
    const base = path.join(frontendDir, specifier.slice(2));
    const url = probe(base);
    if (url) return { url, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
