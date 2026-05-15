"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { NextPairResponse, VoteValue } from "@/lib/supabase";

function salaryLabel(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  const fmt = (n: number) => `$${Math.round(n / 1000)}k`;
  if (min && max) return `${fmt(min)}–${fmt(max)}`;
  if (min) return `${fmt(min)}+`;
  return `up to ${fmt(max!)}`;
}

function VoteButton({
  label,
  active,
  hotkey,
  onClick,
}: {
  label: string;
  active: boolean;
  hotkey: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded border text-sm font-mono transition-colors ${
        active
          ? "bg-primary text-primary-foreground border-primary"
          : "bg-background text-foreground border-border hover:border-foreground"
      }`}
    >
      <span className="opacity-40 mr-1">[{hotkey}]</span> {label}
    </button>
  );
}

// --- Diff highlighting ---

const DIFF_PALETTE = [
  "bg-red-100 text-red-900",
  "bg-blue-100 text-blue-900",
  "bg-amber-100 text-amber-900",
  "bg-emerald-100 text-emerald-900",
  "bg-purple-100 text-purple-900",
  "bg-cyan-100 text-cyan-900",
  "bg-fuchsia-100 text-fuchsia-900",
  "bg-teal-100 text-teal-900",
] as const;

type ColoredWord = { text: string; colorIdx: number | null };

function splitWords(text: string): string[] {
  return text.trim().split(/\s+/).filter(Boolean);
}

function wordDiff(
  leftWords: string[],
  rightWords: string[],
  colorStart: number
): { leftItems: ColoredWord[]; rightItems: ColoredWord[]; nextColor: number } {
  const m = leftWords.length, n = rightWords.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0) as number[]);
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] =
        leftWords[i - 1].toLowerCase() === rightWords[j - 1].toLowerCase()
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);

  type Op = { t: "m"; l: string; r: string } | { t: "L"; w: string } | { t: "R"; w: string };
  const ops: Op[] = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && leftWords[i - 1].toLowerCase() === rightWords[j - 1].toLowerCase()) {
      ops.unshift({ t: "m", l: leftWords[i - 1], r: rightWords[j - 1] }); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ t: "R", w: rightWords[j - 1] }); j--;
    } else {
      ops.unshift({ t: "L", w: leftWords[i - 1] }); i--;
    }
  }

  const leftItems: ColoredWord[] = [], rightItems: ColoredWord[] = [];
  let nextColor = colorStart, oi = 0;
  while (oi < ops.length) {
    const op = ops[oi];
    if (op.t === "m") {
      leftItems.push({ text: op.l, colorIdx: null });
      rightItems.push({ text: op.r, colorIdx: null });
      oi++;
    } else {
      const colorIdx = nextColor % DIFF_PALETTE.length;
      nextColor++;
      const start = oi;
      while (oi < ops.length && ops[oi].t !== "m") oi++;
      for (const gop of ops.slice(start, oi)) {
        if (gop.t === "L") leftItems.push({ text: gop.w, colorIdx });
        else rightItems.push({ text: gop.w, colorIdx });
      }
    }
  }
  return { leftItems, rightItems, nextColor };
}

interface JobDiff {
  titleLeft: ColoredWord[];
  titleRight: ColoredWord[];
  locationLeft: ColoredWord[] | null;
  locationRight: ColoredWord[] | null;
  salaryClassLeft: string;
  salaryClassRight: string;
  snippetLeft: ColoredWord[];
  snippetRight: ColoredWord[];
}

function computeJobDiff(left: NextPairResponse["job_left"], right: NextPairResponse["job_left"]): JobDiff {
  let nextColor = 0;

  const titleDiff = wordDiff(splitWords(left.title), splitWords(right.title), nextColor);
  nextColor = titleDiff.nextColor;

  const locL = left.location ?? "", locR = right.location ?? "";
  let locationLeft: ColoredWord[] | null = null, locationRight: ColoredWord[] | null = null;
  if (locL !== locR) {
    if (locL && locR) {
      const ld = wordDiff(splitWords(locL), splitWords(locR), nextColor);
      locationLeft = ld.leftItems; locationRight = ld.rightItems; nextColor = ld.nextColor;
    } else {
      const colorIdx = nextColor++ % DIFF_PALETTE.length;
      if (locL) locationLeft = [{ text: locL, colorIdx }];
      if (locR) locationRight = [{ text: locR, colorIdx }];
    }
  } else if (locL) {
    locationLeft = [{ text: locL, colorIdx: null }];
    locationRight = [{ text: locR, colorIdx: null }];
  }

  let salaryClassLeft = "", salaryClassRight = "";
  if (left.salary_min !== right.salary_min || left.salary_max !== right.salary_max) {
    const cls = `${DIFF_PALETTE[nextColor % DIFF_PALETTE.length]} rounded px-0.5`;
    nextColor++;
    if (left.salary_min != null || left.salary_max != null) salaryClassLeft = cls;
    if (right.salary_min != null || right.salary_max != null) salaryClassRight = cls;
  }

  const snippetDiff = wordDiff(splitWords(left.snippet), splitWords(right.snippet), nextColor);

  return {
    titleLeft: titleDiff.leftItems,
    titleRight: titleDiff.rightItems,
    locationLeft,
    locationRight,
    salaryClassLeft,
    salaryClassRight,
    snippetLeft: snippetDiff.leftItems,
    snippetRight: snippetDiff.rightItems,
  };
}

function HighlightedWords({ items }: { items: ColoredWord[] }) {
  return (
    <>
      {items.map((item, idx) => (
        <span key={idx}>
          {item.colorIdx !== null ? (
            <span className={`${DIFF_PALETTE[item.colorIdx]} rounded px-0.5`}>{item.text}</span>
          ) : item.text}
          {idx < items.length - 1 ? " " : ""}
        </span>
      ))}
    </>
  );
}

function JobCard({
  job,
  side,
  diff,
}: {
  job: NextPairResponse["job_left"];
  side: "left" | "right";
  diff: JobDiff | null;
}) {
  const salary = salaryLabel(job.salary_min, job.salary_max);
  const isLeft = side === "left";
  const titleWords = diff ? (isLeft ? diff.titleLeft : diff.titleRight) : splitWords(job.title).map(w => ({ text: w, colorIdx: null as null }));
  const locationWords = diff ? (isLeft ? diff.locationLeft : diff.locationRight) : (job.location ? [{ text: job.location, colorIdx: null as null }] : null);
  const salaryClass = diff ? (isLeft ? diff.salaryClassLeft : diff.salaryClassRight) : "";
  const snippetWords = diff ? (isLeft ? diff.snippetLeft : diff.snippetRight) : splitWords(job.snippet).map(w => ({ text: w, colorIdx: null as null }));

  return (
    <div className={`flex-1 border border-border rounded-lg p-5 bg-card ${side === "left" ? "mr-3" : "ml-3"}`}>
      <div className="font-semibold text-foreground text-base leading-snug">
        <HighlightedWords items={titleWords} />
      </div>
      <div className="text-muted-foreground text-sm mt-1 flex flex-wrap items-baseline gap-x-1">
        <span>{job.company}</span>
        {locationWords && locationWords.length > 0 && (
          <>
            <span>·</span>
            <HighlightedWords items={locationWords} />
          </>
        )}
        {salary && (
          <>
            <span>·</span>
            <span className={salaryClass}>{salary}</span>
          </>
        )}
      </div>
      <div className="text-foreground/80 text-sm mt-3 leading-relaxed">
        <HighlightedWords items={snippetWords} />
      </div>
    </div>
  );
}

function sessionId(): string {
  if (typeof window === "undefined") return "";
  if (!window.__compareSessionId) {
    window.__compareSessionId = crypto.randomUUID();
  }
  return window.__compareSessionId;
}

declare global {
  interface Window {
    __compareSessionId?: string;
  }
}

export default function ComparePage() {
  const [pair, setPair] = useState<NextPairResponse | null>(null);
  const [fitVote, setFitVote] = useState<VoteValue | null>(null);
  const [interestVote, setInterestVote] = useState<VoteValue | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextPairRef = useRef<NextPairResponse | null>(null);
  const prefetchingRef = useRef(false);
  const autoAdvanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchPair = useCallback(async (): Promise<NextPairResponse | null> => {
    const res = await fetch("/api/compare/next-pair");
    if (!res.ok) return null;
    return res.json();
  }, []);

  const prefetchNext = useCallback(async () => {
    if (prefetchingRef.current || nextPairRef.current) return;
    prefetchingRef.current = true;
    const next = await fetchPair();
    nextPairRef.current = next;
    prefetchingRef.current = false;
  }, [fetchPair]);

  useEffect(() => {
    fetchPair().then((p) => {
      setPair(p);
      setLoading(false);
    });
  }, [fetchPair]);

  const advance = useCallback(async () => {
    if (!pair || !fitVote || !interestVote || submitting) return;

    setSubmitting(true);
    autoAdvanceTimer.current && clearTimeout(autoAdvanceTimer.current);

    const recordRes = await fetch("/api/compare/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_a_id: pair.job_a_id,
        job_b_id: pair.job_b_id,
        display_left_job_id: pair.display_left_job_id,
        display_right_job_id: pair.display_right_job_id,
        winner_fit: fitVote,
        winner_interest: interestVote,
        pair_type: pair.pair_type,
        selection_mode: pair.selection_mode,
        session_id: sessionId(),
      }),
    });

    if (!recordRes.ok) {
      setError(`Failed to save votes (HTTP ${recordRes.status}). Try again.`);
      setSubmitting(false);
      return;
    }

    if (
      nextPairRef.current &&
      nextPairRef.current.job_a_id === pair.job_a_id &&
      nextPairRef.current.job_b_id === pair.job_b_id
    ) {
      nextPairRef.current = null;
    }

    const next = nextPairRef.current ?? (await fetchPair());
    nextPairRef.current = null;
    prefetchingRef.current = false;

    setPair(next);
    setFitVote(null);
    setInterestVote(null);
    setSubmitting(false);

    setTimeout(prefetchNext, 0);
  }, [pair, fitVote, interestVote, submitting, fetchPair, prefetchNext]);

  useEffect(() => {
    if (fitVote && interestVote) {
      autoAdvanceTimer.current = setTimeout(advance, 300);
    }
    return () => {
      if (autoAdvanceTimer.current) clearTimeout(autoAdvanceTimer.current);
    };
  }, [fitVote, interestVote, advance]);

  useEffect(() => {
    if ((fitVote || interestVote) && !nextPairRef.current) {
      prefetchNext();
    }
  }, [fitVote, interestVote, prefetchNext]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case "1": setFitVote("left"); break;
        case "2": setFitVote("tie"); break;
        case "3": setFitVote("right"); break;
        case "7": setInterestVote("left"); break;
        case "8": setInterestVote("tie"); break;
        case "9": setInterestVote("right"); break;
        case "Enter": if (fitVote && interestVote) advance(); break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fitVote, interestVote, advance]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading…</div>;
  }

  if (!pair) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        No pairs available. Run <code className="mx-1 font-mono text-sm">extract_features.py</code> and{" "}
        <code className="mx-1 font-mono text-sm">synthetic_jobs.py</code> first.
      </div>
    );
  }

  const bothVoted = Boolean(fitVote && interestVote);
  const diff = computeJobDiff(pair.job_left, pair.job_right);

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Job cards */}
      <div className="flex mb-6">
        <JobCard job={pair.job_left} side="left" diff={diff} />
        <div className="flex items-center text-muted-foreground font-light text-lg px-2">vs</div>
        <JobCard job={pair.job_right} side="right" diff={diff} />
      </div>

      {/* Voting */}
      <div className="bg-card rounded-lg border border-border p-5 space-y-4">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground w-20">Interest</span>
          <div className="flex gap-2">
            <VoteButton label="← Left" active={interestVote === "left"} hotkey="7" onClick={() => setInterestVote("left")} />
            <VoteButton label="Tie" active={interestVote === "tie"} hotkey="8" onClick={() => setInterestVote("tie")} />
            <VoteButton label="Right →" active={interestVote === "right"} hotkey="9" onClick={() => setInterestVote("right")} />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground w-20">Fit</span>
          <div className="flex gap-2">
            <VoteButton label="← Left" active={fitVote === "left"} hotkey="1" onClick={() => setFitVote("left")} />
            <VoteButton label="Tie" active={fitVote === "tie"} hotkey="2" onClick={() => setFitVote("tie")} />
            <VoteButton label="Right →" active={fitVote === "right"} hotkey="3" onClick={() => setFitVote("right")} />
          </div>
        </div>
        {error && (
          <div className="text-sm text-destructive pt-1">{error}</div>
        )}
        {!error && bothVoted && !submitting && (
          <div className="text-xs text-muted-foreground pt-1">Auto-advancing… or press Enter</div>
        )}
      </div>

      {/* Status bar */}
      <div className="mt-4 text-xs text-muted-foreground flex gap-4">
        <span>{pair.comparisons_so_far} comparisons</span>
        {pair.mandatory_remaining > 0 && (
          <span className="text-amber-600">{pair.mandatory_remaining} mandatory remaining</span>
        )}
        <span className="ml-auto opacity-50">
          {pair.selection_mode} · {pair.pair_type}
        </span>
      </div>

      {/* Progress bar for mandatory queue */}
      {pair.mandatory_remaining > 0 && (
        <div className="mt-2 h-1 bg-muted rounded overflow-hidden">
          <div
            className="h-full bg-amber-500 transition-all duration-300"
            style={{ width: `${Math.max(5, 100 - (pair.mandatory_remaining / (pair.mandatory_remaining + pair.comparisons_so_far)) * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
