// Run with: npx tsx scripts/dedup-jobs.ts
// Removes duplicate jobs from Supabase, keeping the earliest entry for each URL

import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

async function dedup() {
  const { data: jobs, error } = await supabase
    .from("jobs")
    .select("id, url, title, company, created_at")
    .order("created_at", { ascending: true });

  if (error) {
    console.error("Failed to fetch jobs:", error.message);
    process.exit(1);
  }

  const seen = new Map<string, string>();
  const toDelete: string[] = [];

  for (const job of jobs ?? []) {
    if (!job.url) continue;
    if (seen.has(job.url)) {
      toDelete.push(job.id);
      console.log(`  DUP: ${job.title} @ ${job.company}`);
    } else {
      seen.set(job.url, job.id);
    }
  }

  if (toDelete.length === 0) {
    console.log("No duplicates found.");
    return;
  }

  console.log(`\nDeleting ${toDelete.length} duplicate(s)...`);
  const { error: delError } = await supabase
    .from("jobs")
    .delete()
    .in("id", toDelete);

  if (delError) {
    console.error("Delete failed:", delError.message);
  } else {
    console.log(`Done. Removed ${toDelete.length} duplicates.`);
  }
}

dedup();
