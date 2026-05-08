import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get("x-api-key");
  if (apiKey !== process.env.INGEST_API_KEY) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const { title, company, url, description, source, haiku_score, lib_score,
          salary_min, salary_max, location, posted_at, applicant_count,
          relevance_explanation } = body;

  if (!title || !company) {
    return NextResponse.json({ error: "title and company are required" }, { status: 400 });
  }

  const db = createServiceClient();

  // Deduplicate by URL if provided
  if (url) {
    const { data: existing } = await db
      .from("jobs")
      .select("id")
      .eq("url", url)
      .limit(1)
      .single();

    if (existing) {
      return NextResponse.json({ id: existing.id, deduplicated: true }, { status: 200 });
    }
  }

  const { data, error } = await db
    .from("jobs")
    .insert({
      title, company, url: url ?? null, description: description ?? null,
      source: source ?? null, stage: "new", outcome: "active",
      haiku_score: haiku_score ?? null, lib_score: lib_score ?? null,
      salary_min: salary_min ?? null, salary_max: salary_max ?? null,
      location: location ?? null, posted_at: posted_at ?? null,
      applicant_count: applicant_count ?? null,
      relevance_explanation: relevance_explanation ?? null,
    })
    .select()
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ id: data.id }, { status: 201 });
}
