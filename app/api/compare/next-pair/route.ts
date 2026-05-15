import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase";
import type { CompareJob, NextPairResponse, PairType, SelectionMode } from "@/lib/supabase";

const JOB_SELECT = "id,title,company,location,salary_min,salary_max,description,synthetic,synthetic_spec";
const SCORED_SELECT = "id,title,company,location,salary_min,salary_max,description,synthetic,act";
const MIN_DESC_LEN = 500;
const PROBE_INTERVAL = 5;
const UNCERTAINTY_MIN_COMPARISONS = 30;
const MAX_JOB_COMPARISONS = 30;
const COOLDOWN_PAIRS = 20;
const MANDATORY_COMPARISONS_REQUIRED = 2;

function snippet(text: string | null, maxLen = 400): string {
  if (!text) return "";
  if (text.length <= maxLen) return text;
  const truncated = text.slice(0, maxLen);
  const lastPeriod = truncated.lastIndexOf(".");
  return lastPeriod > maxLen * 0.6 ? truncated.slice(0, lastPeriod + 1) : truncated + "…";
}

function toCompareJob(job: Record<string, unknown>): CompareJob {
  return {
    id: job.id as string,
    title: job.title as string,
    company: job.company as string,
    location: (job.location as string | null) ?? null,
    salary_min: (job.salary_min as number | null) ?? null,
    salary_max: (job.salary_max as number | null) ?? null,
    snippet: snippet(job.description as string | null),
    synthetic: Boolean(job.synthetic),
  };
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

function canonicalPair(a: string, b: string): [string, string] {
  return a < b ? [a, b] : [b, a];
}

function randomOf<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function shuffle<T>(arr: T[]): T[] {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export async function GET() {
  try {
    return await handleGET();
  } catch (err) {
    console.error("[compare/next-pair]", err);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

async function handleGET() {
  const db = createServiceClient();

  const { data: allComparisons, error: compErr } = await db
    .from("comparisons")
    .select("id,job_a_id,job_b_id,pair_type,created_at")
    .order("created_at", { ascending: false });

  if (compErr) return NextResponse.json({ error: compErr.message }, { status: 500 });

  const comparisons = allComparisons ?? [];
  const comparisonsTotal = comparisons.length;

  const jobCompCount: Record<string, number> = {};
  for (const c of comparisons) {
    jobCompCount[c.job_a_id] = (jobCompCount[c.job_a_id] ?? 0) + 1;
    jobCompCount[c.job_b_id] = (jobCompCount[c.job_b_id] ?? 0) + 1;
  }

  const recentPairKeys = new Set(
    comparisons.slice(0, COOLDOWN_PAIRS).flatMap((c) => [
      `${c.job_a_id}:${c.job_b_id}`,
      `${c.job_b_id}:${c.job_a_id}`,
    ])
  );

  function pairOnCooldown(a: string, b: string): boolean {
    return recentPairKeys.has(`${a}:${b}`) || recentPairKeys.has(`${b}:${a}`);
  }

  const historicalProbePairKeys = new Set(
    comparisons.filter((c) => c.pair_type === "probe").map((c) => `${c.job_a_id}:${c.job_b_id}`)
  );
  function probePairAlreadyCompared(a: string, b: string): boolean {
    const [ca, cb] = canonicalPair(a, b);
    return historicalProbePairKeys.has(`${ca}:${cb}`);
  }

  const nonProbeCount = comparisons.filter((c) => c.pair_type !== "probe").length;
  const injectProbe = nonProbeCount > 0 && nonProbeCount % PROBE_INTERVAL === 0;

  if (injectProbe) {
    const result = await selectProbePair(db, jobCompCount, probePairAlreadyCompared, comparisonsTotal);
    if (result) return NextResponse.json(result);
  }

  // Mandatory queue: active applied/in-process jobs using stage+outcome
  const [mandatoryResult, frontierHighResult, frontierLowResult, recentResult] = await Promise.all([
    db.from("jobs").select(JOB_SELECT)
      .in("stage", ["applied", "acked", "screened", "interviewed", "offered"])
      .eq("outcome", "active")
      .eq("synthetic", false),
    db.from("jobs_scored").select(SCORED_SELECT).eq("synthetic", false).order("act", { ascending: false }).limit(100),
    db.from("jobs_scored").select(SCORED_SELECT).eq("synthetic", false).order("act", { ascending: true }).limit(100),
    db.from("jobs").select(JOB_SELECT).eq("synthetic", false).order("created_at", { ascending: false }).limit(50),
  ]);

  const seen = new Set<string>();
  const pool: Record<string, unknown>[] = [];
  const mandatoryIds = new Set<string>();

  for (const job of (mandatoryResult.data ?? [])) {
    if (!seen.has(job.id)) {
      seen.add(job.id);
      mandatoryIds.add(job.id);
      pool.push(job);
    }
  }
  for (const job of [
    ...(frontierHighResult.data ?? []),
    ...(frontierLowResult.data ?? []),
    ...(recentResult.data ?? []),
  ]) {
    if (!seen.has(job.id) && (job.description?.length ?? 0) >= MIN_DESC_LEN) {
      seen.add(job.id);
      pool.push(job);
    }
  }

  const mandatoryUnderserved = pool.filter(
    (j) => mandatoryIds.has(j.id as string) && (jobCompCount[j.id as string] ?? 0) < MANDATORY_COMPARISONS_REQUIRED
  );
  const mandatoryRemaining = mandatoryUnderserved.length;

  if (mandatoryRemaining > 0) {
    const anchor = mandatoryUnderserved[0];
    const partner = pool.find(
      (j) => j.id !== anchor.id && !pairOnCooldown(anchor.id as string, j.id as string)
    );
    if (partner) {
      return NextResponse.json(
        buildResponse(anchor, partner, "mandatory", "mandatory", comparisonsTotal, mandatoryRemaining - 1)
      );
    }
  }

  const eligible = pool.filter(
    (j) => !mandatoryIds.has(j.id as string) && (jobCompCount[j.id as string] ?? 0) < MAX_JOB_COMPARISONS
  );

  if (comparisonsTotal >= UNCERTAINTY_MIN_COMPARISONS) {
    const uncertainResult = await selectUncertainPair(db, eligible, jobCompCount, pairOnCooldown);
    if (uncertainResult) {
      return NextResponse.json({
        ...uncertainResult,
        comparisons_so_far: comparisonsTotal,
        mandatory_remaining: mandatoryRemaining,
      });
    }
  }

  const sorted = [...eligible].sort((a, b) => {
    const aAct = (a.act as number | undefined) ?? 0;
    const bAct = (b.act as number | undefined) ?? 0;
    return bAct - aAct;
  });
  const topTertile = sorted.slice(0, Math.ceil(sorted.length / 3));
  const bottomTertile = sorted.slice(Math.floor((sorted.length * 2) / 3));

  if (topTertile.length > 0 && bottomTertile.length > 0) {
    const shuffledTop = shuffle(topTertile);
    const shuffledBottom = shuffle(bottomTertile);
    for (const jobA of shuffledTop) {
      for (const jobB of shuffledBottom) {
        if (jobA.id !== jobB.id && !pairOnCooldown(jobA.id as string, jobB.id as string)) {
          return NextResponse.json(
            buildResponse(jobA, jobB, "real", "stratified", comparisonsTotal, mandatoryRemaining)
          );
        }
      }
    }
  }

  const anyPair = findAnyPair(eligible, pairOnCooldown);
  if (anyPair) {
    return NextResponse.json(
      buildResponse(anyPair[0], anyPair[1], "real", "stratified", comparisonsTotal, mandatoryRemaining)
    );
  }

  return NextResponse.json({ error: "No eligible pairs found" }, { status: 404 });
}

async function selectProbePair(
  db: ReturnType<typeof createServiceClient>,
  jobCompCount: Record<string, number>,
  pairAlreadyCompared: (a: string, b: string) => boolean,
  comparisonsTotal: number
): Promise<NextPairResponse | null> {
  const { data: probes } = await db
    .from("jobs")
    .select(`${JOB_SELECT},synthetic_spec`)
    .eq("synthetic", true)
    .eq("source", "synthetic_probe");

  if (!probes || probes.length < 2) return null;

  const groups: Record<string, typeof probes> = {};
  for (const probe of probes) {
    const spec = probe.synthetic_spec as Record<string, unknown> | null;
    const group = (spec?.probe_group as string) ?? "unknown";
    groups[group] = groups[group] ?? [];
    groups[group].push(probe);
  }

  const groupCounts: Record<string, number> = {};
  for (const [group, members] of Object.entries(groups)) {
    const ids = new Set(members.map((m) => m.id));
    groupCounts[group] = Object.entries(jobCompCount)
      .filter(([id]) => ids.has(id))
      .reduce((sum, [, count]) => sum + count, 0);
  }

  const leastGroup = Object.entries(groupCounts)
    .filter(([group]) => groups[group].length === 2)
    .sort(([, a], [, b]) => a - b)
    .find(([group]) => {
      const [a, b] = groups[group];
      return !pairAlreadyCompared(a.id, b.id);
    });

  if (!leastGroup) return null;

  const [probeA, probeB] = groups[leastGroup[0]];
  return buildResponse(probeA, probeB, "probe", "probe", comparisonsTotal, 0);
}

async function selectUncertainPair(
  db: ReturnType<typeof createServiceClient>,
  eligible: Record<string, unknown>[],
  jobCompCount: Record<string, number>,
  pairOnCooldown: (a: string, b: string) => boolean
): Promise<Omit<NextPairResponse, "comparisons_so_far" | "mandatory_remaining"> | null> {
  const { data: modelStates } = await db.from("model_state").select("*");
  if (!modelStates || modelStates.length === 0) return null;

  const fitState = modelStates.find((s) => s.dimension === "fit");
  const interestState = modelStates.find((s) => s.dimension === "interest");
  if (!fitState && !interestState) return null;

  const eligibleIds = eligible.map((j) => j.id as string);
  const { data: features } = await db
    .from("job_features")
    .select("*")
    .in("job_id", eligibleIds);

  if (!features || features.length < 2) return null;

  const featureMap: Record<string, Record<string, number>> = {};
  for (const row of features) {
    featureMap[row.job_id] = row;
  }

  function standardizeJob(feat: Record<string, number>, names: string[], means: number[], scales: number[]): number[] {
    return names.map((name, i) => ((feat[name] ?? 0) - means[i]) / (scales[i] || 1));
  }

  function pairUncertainty(aId: string, bId: string): number {
    const fa = featureMap[aId];
    const fb = featureMap[bId];
    if (!fa || !fb) return 0;

    let total = 0;
    for (const state of [fitState, interestState]) {
      if (!state) continue;
      const names = state.feature_names as string[];
      const coefs = state.coefficients as number[];
      const means = state.feature_means as number[];
      const scales = state.feature_scales as number[];
      const intercept = state.intercept as number;
      const stdA = standardizeJob(fa, names, means, scales);
      const stdB = standardizeJob(fb, names, means, scales);
      let dot = intercept;
      for (let i = 0; i < names.length; i++) {
        dot += coefs[i] * (stdA[i] - stdB[i]);
      }
      const p = sigmoid(dot);
      total += 1 - Math.abs(2 * p - 1);
    }
    return total;
  }

  const candidates = eligible.filter((j) => featureMap[j.id as string]);
  let bestScore = -1;
  let bestPair: [Record<string, unknown>, Record<string, unknown>] | null = null;

  for (let i = 0; i < candidates.length; i++) {
    for (let j = i + 1; j < candidates.length; j++) {
      const a = candidates[i];
      const b = candidates[j];
      if (pairOnCooldown(a.id as string, b.id as string)) continue;
      const score = pairUncertainty(a.id as string, b.id as string);
      if (score > bestScore) {
        bestScore = score;
        bestPair = [a, b];
      }
    }
  }

  if (!bestPair) return null;
  return buildResponse(bestPair[0], bestPair[1], "real", "uncertainty", 0, 0);
}

function findAnyPair(
  pool: Record<string, unknown>[],
  pairOnCooldown: (a: string, b: string) => boolean
): [Record<string, unknown>, Record<string, unknown>] | null {
  for (let i = 0; i < pool.length; i++) {
    for (let j = i + 1; j < pool.length; j++) {
      if (!pairOnCooldown(pool[i].id as string, pool[j].id as string)) {
        return [pool[i], pool[j]];
      }
    }
  }
  return null;
}

function buildResponse(
  jobA: Record<string, unknown>,
  jobB: Record<string, unknown>,
  pairType: PairType,
  selectionMode: SelectionMode,
  comparisonsTotal: number,
  mandatoryRemaining: number
): NextPairResponse {
  if ((jobA.id as string) === (jobB.id as string)) {
    throw new Error(`self-pair selected: ${jobA.id as string}`);
  }
  const displayLeft = Math.random() < 0.5 ? jobA : jobB;
  const displayRight = displayLeft === jobA ? jobB : jobA;
  const [canonA, canonB] = canonicalPair(jobA.id as string, jobB.id as string);

  return {
    job_left: toCompareJob(displayLeft),
    job_right: toCompareJob(displayRight),
    job_a_id: canonA,
    job_b_id: canonB,
    display_left_job_id: displayLeft.id as string,
    display_right_job_id: displayRight.id as string,
    pair_type: pairType,
    selection_mode: selectionMode,
    comparisons_so_far: comparisonsTotal,
    mandatory_remaining: mandatoryRemaining,
  };
}

// suppress unused import warning — randomOf is used as a utility
void (randomOf as unknown);
