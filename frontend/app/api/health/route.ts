import { NextResponse } from "next/server";

/**
 * Pure proxy to the backend /health endpoint.
 *
 * No filesystem writes, no process listeners, no logging, no side effects.
 * Forwards the backend's JSON body and status unchanged; returns 502 only
 * when the backend is unreachable (including the 5s timeout).
 */
export async function GET(): Promise<NextResponse> {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const upstream = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ ok: false, error: "backend unreachable" }, { status: 502 });
  }
}
