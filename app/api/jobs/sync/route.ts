import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase";

// Stage watermark for progress events (never downgrade)
const STAGE_MAP: Record<string, string> = {
  applied:      "applied",
  phone_screen: "screened",
  interview:    "interviewed",
  interviewing: "interviewed",
  offer:        "offered",
};

// Outcome for terminal events
const OUTCOME_MAP: Record<string, string> = {
  rejected:  "rejected",
  withdrawn: "withdrawn",
};

const KNOWN_EVENTS = new Set([
  "applied", "phone_screen", "interview", "interviewing", "offer", "rejected", "withdrawn",
]);

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get("x-api-key");
  if (apiKey !== process.env.INGEST_API_KEY) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { url, status, title, company, description } = await req.json();
  if (!url || !status) {
    return NextResponse.json({ error: "url and status required" }, { status: 400 });
  }

  const event = status.toLowerCase();
  if (!KNOWN_EVENTS.has(event)) {
    return NextResponse.json({ error: `Unknown status: ${status}` }, { status: 400 });
  }

  const db = createServiceClient();

  // Find existing job by URL
  const { data: existing } = await db
    .from("jobs")
    .select("id")
    .eq("url", url)
    .limit(1)
    .single();

  if (existing) {
    const patch: Record<string, string> = {};
    const newStage = STAGE_MAP[event];
    const newOutcome = OUTCOME_MAP[event];
    if (newStage) patch.stage = newStage;
    if (newOutcome) patch.outcome = newOutcome;
    await db.from("jobs").update(patch).eq("id", existing.id);
    return NextResponse.json({ id: existing.id, action: "updated" });
  }

  // Job not in web UI yet (manually applied outside scraper) — create it
  if (title && company) {
    const newStage = STAGE_MAP[event] ?? "new";
    const newOutcome = OUTCOME_MAP[event] ?? "active";
    const { data, error } = await db
      .from("jobs")
      .insert({
        title, company, url, stage: newStage, outcome: newOutcome,
        source: "discord", description: description ?? null,
      })
      .select()
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ id: data.id, action: "created" });
  }

  // URL not found and no title/company to create — still a success, just not synced
  return NextResponse.json({ action: "not_found" }, { status: 200 });
}
