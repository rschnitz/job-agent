"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, User } from "lucide-react";

const DEFAULT_RESUME = `MIT BS/MS Computer Science and Electrical Engineering.

I help engineering teams deliver production systems companies can rely on.

Experience:
- Principal Engineer, Lexicon Branding (2025-present)
  Led architecture and delivery of a production AI platform translating decades of proprietary research and a corpus of over half a million evaluated candidate names into structured naming analysis. Designed full-stack system architecture (Next.js, Supabase/PostgreSQL, LLM workflows).

- Principal Engineer, schnitz.org (2024-present)
  Independent consulting: Generous Energy (ML-driven electricity trading, ERCOT markets), ShockProof! Training (AI-enabled workflow platform), CarMagic (platform migration strategy, 20-30% cost reduction).

- Engineering Manager, Wells Fargo Bank (2004-2025)
  Led AuthHub cloud-native enterprise authentication platform. Scaled teams 0→20+. $2M+ annual fraud savings. 25% developer productivity increase. Tens of millions of daily users. Java/Spring Boot, MongoDB, distributed systems.

- Director of Software Development, Round1, San Francisco
  Fintech platform for institutional investors. Algorithmic auction system. US and international patents.

- Senior Engineer, Samsung Advanced Media Laboratory
  Multiple US and international patents. Reduced product development cycles by six months.

Key narrative: "I develop whole engineers who take ownership beyond code — engineers who lead projects, mentor others, drive quality improvements, and own their systems in production."`;

const DEFAULT_SKILLS = `Java, Python, Shell, C++, Spring Boot, REST APIs, PostgreSQL, MongoDB, Redis, Kafka, Distributed systems, Microservices, API platforms, Authentication systems, Observability, Reliability engineering, CI/CD pipelines, Automated testing, Code generation, Developer productivity tooling, LLM integration, AI platform architecture, Data pipelines, Next.js, Supabase`;

const DEFAULT_PREFERENCES = `Target roles: Engineering Manager, Senior EM, Director of Engineering, Head of Engineering, Principal/Staff Engineer.

Location: Piedmont/Bay Area — SF, Oakland, Berkeley preferred. Remote OK. South Bay acceptable.

Target comp: $200k+ total compensation baseline.

Industries: Fintech, authentication/identity, platform engineering, AI/ML, developer tools, energy trading.

Values: Meaningful mission, strong people development culture, collaborative technical decision-making.

Cover letter style: Direct, substantive, technically confident but people-focused. Lead with specific impact, not generic enthusiasm.`;

export default function ProfilePage() {
  const [resumeText, setResumeText] = useState("");
  const [skills, setSkills] = useState("");
  const [preferences, setPreferences] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/profile")
      .then((r) => r.json())
      .then((data) => {
        setResumeText(data.resume_text || DEFAULT_RESUME);
        setSkills(data.skills || DEFAULT_SKILLS);
        setPreferences(data.preferences || DEFAULT_PREFERENCES);
        setLoading(false);
      });
  }, []);

  async function save() {
    setSaving(true);
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_text: resumeText, skills, preferences }),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-40 rounded-xl bg-card border border-border animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <User className="h-4 w-4 text-primary" />
          <h1 className="text-xl font-semibold">Your Profile</h1>
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saved ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5" />
              Saved
            </>
          ) : saving ? "Saving..." : "Save profile"}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        This is your background. The AI reads this every time you chat — the richer this is, the better your cover letters and interview prep will be.
      </p>

      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Background & Experience</CardTitle>
            <p className="text-xs text-muted-foreground">Your resume, work history, education, and key narratives</p>
          </CardHeader>
          <CardContent>
            <Textarea
              rows={12}
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              className="font-mono text-xs leading-relaxed resize-y"
              placeholder="Paste your resume or describe your background..."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Skills</CardTitle>
            <p className="text-xs text-muted-foreground">Tools, technologies, and capabilities worth highlighting</p>
          </CardHeader>
          <CardContent>
            <Textarea
              rows={4}
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              className="text-sm leading-relaxed resize-y"
              placeholder="e.g. Salesforce, cold calling, Python, technical demos..."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Job Preferences</CardTitle>
            <p className="text-xs text-muted-foreground">Target roles, location, comp, industries, and style notes for cover letters</p>
          </CardHeader>
          <CardContent>
            <Textarea
              rows={6}
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              className="text-sm leading-relaxed resize-y"
              placeholder="e.g. SDR/BDR at SaaS companies, SF Bay Area, $80k+..."
            />
          </CardContent>
        </Card>

        <div className="flex justify-end pt-1">
          <Button onClick={save} disabled={saving}>
            {saved ? (
              <>
                <CheckCircle2 className="h-4 w-4" />
                Saved
              </>
            ) : saving ? "Saving..." : "Save profile"}
          </Button>
        </div>
      </div>
    </div>
  );
}
