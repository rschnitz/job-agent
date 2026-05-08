"use client";

import { useEffect, useMemo, useState } from "react";
import { supabase, type Job } from "@/lib/supabase";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

// ── helpers ────────────────────────────────────────────────────────────────

function fmtSalary(j: Job): string {
  const { salary_min: lo, salary_max: hi } = j;
  if (lo && hi) return `$${Math.round(lo / 1000)}–${Math.round(hi / 1000)}K`;
  if (lo) return `$${Math.round(lo / 1000)}K+`;
  if (hi) return `≤$${Math.round(hi / 1000)}K`;
  return "—";
}

function normalizeTitle(t: string): string {
  return t
    .toLowerCase()
    .replace(/\s*[\(\|].*$/g, "")       // strip trailing (Remote), | NYC, etc.
    .replace(/\s*[-–]\s*(remote|.{0,20})$/i, "")  // strip - San Francisco etc.
    .replace(/[^a-z0-9 ]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

type FreshClass = "fresh" | "warn" | "stale" | "unknown";

function freshness(j: Job): { label: string; cls: FreshClass; fallback: boolean } {
  const ts = j.last_refreshed_at ?? j.posted_at;
  if (!ts) return { label: "unknown", cls: "unknown", fallback: false };
  const age = Math.floor((Date.now() - new Date(ts).getTime()) / 86_400_000);
  const fallback = !j.last_refreshed_at;
  const cls: FreshClass = age <= 7 ? "fresh" : age <= 21 ? "warn" : "stale";
  return { label: `${age}d${fallback ? "†" : ""}`, cls, fallback };
}

const FRESH_CLS: Record<FreshClass, string> = {
  fresh: "text-green-700 font-semibold",
  warn: "text-amber-600 font-semibold",
  stale: "text-red-600 font-semibold",
  unknown: "text-red-600 font-semibold",
};

// ── sub-components ─────────────────────────────────────────────────────────

function SectionCallout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 text-xs text-amber-800 mb-3">
      <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-card border border-border rounded-lg px-5 py-3 text-center">
      <div className="text-2xl font-bold text-primary tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}

function resumeVariant(url: string | null): string {
  if (!url) return "—";
  const parts = url.split("/");
  // Path: .../RAS/<Variant>/RaySchnitzler.pdf → second-to-last segment
  const folder = parts[parts.length - 2] ?? "";
  return folder || "—";
}

interface TableProps {
  jobs: Job[];
  warnCompanies?: Set<string>;   // multi-apply warning
  dupGroups?: Map<string, Job[]>; // duplicate title warning
  showResume?: boolean;
}

function PipelineTable({ jobs, warnCompanies = new Set(), dupGroups = new Map(), showResume = false }: TableProps) {
  if (jobs.length === 0) {
    return <p className="text-sm text-muted-foreground italic">None.</p>;
  }

  const dupKeys = new Set<string>();
  for (const [, group] of dupGroups) {
    if (group.length > 1) group.forEach((j) => dupKeys.add(j.id));
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/60 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            <th className="px-3 py-2 text-left">J-ID</th>
            <th className="px-3 py-2 text-left">Fit</th>
            <th className="px-3 py-2 text-left">Interest</th>
            <th className="px-3 py-2 text-left">Salary</th>
            <th className="px-3 py-2 text-left">Company</th>
            <th className="px-3 py-2 text-left">Role</th>
            {showResume && <th className="px-3 py-2 text-left">Resume</th>}
            <th className="px-3 py-2 text-left">Last checked</th>
            <th className="px-3 py-2 text-left">Notes</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j, i) => {
            const fresh = freshness(j);
            const companyKey = j.company.toLowerCase();
            const multiApply = warnCompanies.has(companyKey);
            const isDup = dupKeys.has(j.id);

            return (
              <tr
                key={j.id}
                className={cn(
                  "border-t border-border transition-colors hover:bg-accent/30",
                  i % 2 === 0 ? "bg-background" : "bg-muted/20"
                )}
              >
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                  {j.url ? (
                    <a
                      href={j.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline flex items-center gap-1"
                    >
                      {j.ras_id ?? "—"}
                      <ExternalLink className="h-2.5 w-2.5" />
                    </a>
                  ) : (
                    j.ras_id ?? "—"
                  )}
                </td>
                <td className="px-3 py-2 font-semibold tabular-nums">{j.ras_fit ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{j.ras_interest ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{fmtSalary(j)}</td>
                <td className="px-3 py-2">
                  <span className="font-medium">{j.company}</span>
                  {multiApply && (
                    <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0 bg-blue-100 text-blue-700">
                      multi-apply
                    </Badge>
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  <span className="line-clamp-2">{j.title}</span>
                  {isDup && (
                    <span className="flex items-center gap-1 text-[11px] text-amber-600 mt-0.5">
                      <AlertTriangle className="h-3 w-3" />
                      possible duplicate — verify ATS URL
                    </span>
                  )}
                </td>
                {showResume && (
                  <td className="px-3 py-2 text-xs font-mono text-muted-foreground whitespace-nowrap">
                    {resumeVariant(j.resume_url)}
                  </td>
                )}
                <td className="px-3 py-2">
                  <span className={FRESH_CLS[fresh.cls]}>{fresh.label}</span>
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs">
                  {j.notes ?? ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── page ───────────────────────────────────────────────────────────────────

export default function PipelinePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      // Fetch applied + ready (any fit), and high-fit new jobs
      const { data: activePipeline } = await supabase
        .from("jobs")
        .select("*")
        .in("stage", ["applied", "ready"])
        .eq("outcome", "active");

      const { data: highFit } = await supabase
        .from("jobs")
        .select("*")
        .gte("ras_fit", 8)
        .eq("stage", "new")
        .eq("outcome", "active");

      const all = [...(activePipeline ?? []), ...(highFit ?? [])];
      // deduplicate by id
      const seen = new Set<string>();
      const deduped: Job[] = [];
      for (const j of all) {
        if (!seen.has(j.id)) { seen.add(j.id); deduped.push(j); }
      }
      setJobs(deduped);
      setLoading(false);
    }
    load();
  }, []);

  const { applied, ready, fit8, appliedByCompany, dupGroups } = useMemo(() => {
    const applied = jobs
      .filter((j) => j.stage === "applied")
      .sort((a, b) => (b.ras_fit ?? 0) - (a.ras_fit ?? 0) || (b.ras_interest ?? 0) - (a.ras_interest ?? 0));

    const ready = jobs
      .filter((j) => j.stage === "ready")
      .sort((a, b) => (b.ras_fit ?? 0) - (a.ras_fit ?? 0) || (b.ras_interest ?? 0) - (a.ras_interest ?? 0));

    const fit8 = jobs
      .filter((j) => (j.ras_fit ?? 0) >= 8 && j.stage === "new")
      .sort((a, b) => (b.ras_fit ?? 0) - (a.ras_fit ?? 0) || (b.ras_interest ?? 0) - (a.ras_interest ?? 0));

    // Multi-apply: companies with 2+ applied jobs
    const countByCompany = new Map<string, number>();
    for (const j of applied) {
      const k = j.company.toLowerCase();
      countByCompany.set(k, (countByCompany.get(k) ?? 0) + 1);
    }
    const appliedByCompany = new Set<string>(
      [...countByCompany.entries()].filter(([, n]) => n > 1).map(([k]) => k)
    );

    // Duplicate detection: same (company, normalizedTitle) in fit8
    const dupGroups = new Map<string, Job[]>();
    for (const j of fit8) {
      const k = `${j.company.toLowerCase()}:${normalizeTitle(j.title)}`;
      if (!dupGroups.has(k)) dupGroups.set(k, []);
      dupGroups.get(k)!.push(j);
    }

    return { applied, ready, fit8, appliedByCompany, dupGroups };
  }, [jobs]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-7xl">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold">Application Pipeline</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Applied · Ready to submit · Fit=8 unprepped &nbsp;·&nbsp;
            Last checked: <span className="text-green-700 font-semibold">green ≤7d</span>{" "}
            <span className="text-amber-600 font-semibold">amber ≤21d</span>{" "}
            <span className="text-red-600 font-semibold">red &gt;21d</span> &nbsp;†&nbsp;= no check_open run yet
          </p>
        </div>
      </div>

      <div className="flex gap-4 mb-8">
        <StatBox label="Applied" value={applied.length} />
        <StatBox label="Ready to submit" value={ready.length} />
        <StatBox label="Fit=8 unprepped" value={fit8.length} />
      </div>

      {/* Applied */}
      <section className="mb-8">
        <h2 className="text-base font-semibold mb-2">Applied ({applied.length})</h2>
        <PipelineTable jobs={applied} warnCompanies={appliedByCompany} showResume />
      </section>

      {/* Ready to Submit */}
      <section className="mb-8">
        <h2 className="text-base font-semibold mb-2">Ready to Submit ({ready.length})</h2>
        <SectionCallout>
          Confirm each posting is still open before submitting. † means no check_open run yet — do not submit blind.
          Set <code>stage=&apos;ready&apos;</code> on a job once its cover letter PDF is in the company folder.
        </SectionCallout>
        <PipelineTable jobs={ready} showResume />
      </section>

      {/* Fit=8 Unprepped */}
      <section className="mb-8">
        <h2 className="text-base font-semibold mb-2">Fit=8 Unprepped ({fit8.length})</h2>
        {appliedByCompany.size > 0 && (
          <SectionCallout>
            <strong>Multi-apply:</strong> companies with 2+ submitted apps are flagged in the Applied table.
            Check those before adding more applications to the same company.
          </SectionCallout>
        )}
        <PipelineTable jobs={fit8} warnCompanies={appliedByCompany} dupGroups={dupGroups} />
      </section>
    </div>
  );
}
