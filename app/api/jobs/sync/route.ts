import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase";

// Maps Discord bot statuses → web UI statuses
const STATUS_MAP: Record<string, string> = {
  applied:      "applied",
  phone_screen: "interviewing",
  interview:    "interviewing",
  interviewing: "interviewing",
  offer:        "offer",
  rejected:     "rejected",
  withdrawn:    "rejected",
};

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

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get("x-api-key");
  if (apiKey !== process.env.INGEST_API_KEY) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { url, status, title, company, description } = await req.json();
  if (!url || !status) {
    return NextResponse.json({ error: "url and status required" }, { status: 400 });
  }

  const webStatus = STATUS_MAP[status.toLowerCase()];
  if (!webStatus) {
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
    const patch: Record<string, string> = { status: webStatus };
    const newStage = STAGE_MAP[status.toLowerCase()];
    const newOutcome = OUTCOME_MAP[status.toLowerCase()];
    if (newStage) patch.stage = newStage;
    if (newOutcome) patch.outcome = newOutcome;
    await db.from("jobs").update(patch).eq("id", existing.id);
    return NextResponse.json({ id: existing.id, action: "updated", status: webStatus });
  }

  // Job not in web UI yet (manually applied outside scraper) — create it
  if (title && company) {
    const newStage = STAGE_MAP[status.toLowerCase()] ?? "new";
    const newOutcome = OUTCOME_MAP[status.toLowerCase()] ?? "active";
    const { data, error } = await db
      .from("jobs")
      .insert({
        title, company, url, status: webStatus, stage: newStage, outcome: newOutcome,
        source: "discord", description: description ?? null,
      })
      .select()
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ id: data.id, action: "created", status: webStatus });
  }

  // URL not found and no title/company to create — still a success, just not synced
  return NextResponse.json({ action: "not_found" }, { status: 200 });
}
