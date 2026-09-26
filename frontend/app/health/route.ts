import { NextResponse } from "next/server";

export async function GET(): Promise<NextResponse> {
  return NextResponse.json({ status: "ok", service: "lexi-ai-legal-assistant" }, { status: 200 });
}
