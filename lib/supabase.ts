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

export type JobStatus =
  | "new"
  | "saved"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected";

export type Job = {
  id: string;
  title: string;
  company: string;
  url: string | null;
  description: string | null;
  source: string | null;
  status: JobStatus;
  fit_score: number | null;
  relevance_score: number | null;
  relevance_explanation: string | null;
  fit_explanation: string | null;
  salary_min: number | null;
  salary_max: number | null;
  bonus_or_commission_est: number | null;
  equity_est: number | null;
  location: string | null;
  remote_days: number | null;
  posted_at: string | null;
  applicant_count: number | null;
  notes: string | null;
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

export type Conversation = {
  id: string;
  job_id: string | null;
  messages: Message[];
  created_at: string;
};
