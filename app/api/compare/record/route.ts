import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase";
import type { RecordRequest } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  const body: RecordRequest = await req.json();
  const {
    job_a_id,
    job_b_id,
    display_left_job_id,
    display_right_job_id,
    winner_fit,
    winner_interest,
    pair_type,
    selection_mode,
    session_id,
  } = body;

  if (!job_a_id || !job_b_id || !winner_fit || !winner_interest) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const [canonA, canonB] = job_a_id < job_b_id ? [job_a_id, job_b_id] : [job_b_id, job_a_id];

  const db = createServiceClient();

  const { error } = await db.from("comparisons").insert({
    job_a_id: canonA,
    job_b_id: canonB,
    display_left_job_id,
    display_right_job_id,
    winner_fit,
    winner_interest,
    pair_type,
    selection_mode,
    session_id: session_id ?? null,
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const { count } = await db
    .from("comparisons")
    .select("*", { count: "exact", head: true });

  return NextResponse.json({ ok: true, comparisons_so_far: count ?? 0 });
}
