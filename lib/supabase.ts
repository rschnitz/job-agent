import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// Server-side client with elevated privileges (for API routes)
export function createServiceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
}

export type Stage =
  | "new"
  | "ready"
  | "applied"
  | "acked"
  | "screened"
  | "interviewed"
  | "offered";

export type Outcome =
  | "active"
  | "ghosted"
  | "rejected"
  | "withdrawn"
  | "closed"
  | "accepted"
  | "declined";

export type Job = {
  id: string;
  ras_id: string | null;
  title: string;
  company: string;
  url: string | null;
  description: string | null;
  source: string | null;
  stage: Stage | null;
  outcome: Outcome | null;
  haiku_score: number | null;
  lib_score: number | null;
  ras_fit: number | null;
  fit_explanation: string | null;
  ras_interest: number | null;
  relevance_explanation: string | null;
  salary_min: number | null;
  salary_max: number | null;
  bonus_or_commission_est: number | null;
  equity_est: number | null;
  location: string | null;
  remote_days: number | null;
  posted_at: string | null;
  applicant_count: number | null;
  rejection_reason: string | null;
  notes: string | null;
  last_refreshed_at: string | null;
  cover_letter_url: string | null;
  resume_url: string | null;
  created_at: string;
};

export type Profile = {
  id: string;
  resume_text: string | null;
  skills: string | null;
  preferences: string | null;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
};

export function jobDisplayStatus(job: Pick<Job, "stage" | "outcome">): string {
  if (job.outcome && job.outcome !== "active") return job.outcome;
  return job.stage ?? "new";
}

export type Conversation = {
  id: string;
  job_id: string | null;
  messages: Message[];
  created_at: string;
};
