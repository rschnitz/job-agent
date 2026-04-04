import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";
import { homedir } from "os";

const CACHE_DIR = join(homedir(), ".cache", "job-search", "postings");

function jobIdFromUrl(url: string): string | null {
  const match = url.match(/\/view\/(\d+)/);
  return match ? match[1] : null;
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) {
    return NextResponse.json({ error: "url parameter required" }, { status: 400 });
  }

  const jobId = jobIdFromUrl(url);
  if (!jobId) {
    return NextResponse.json({ error: "could not extract job ID from URL" }, { status: 400 });
  }

  const htmlPath = join(CACHE_DIR, jobId, "page.html");
  try {
    const html = await readFile(htmlPath, "utf-8");

    // Extract just the job description section from the full page HTML
    // Look for common LinkedIn job description containers
    const selectors = [
      /class="show-more-less-html__markup[^"]*"[^>]*>([\s\S]*?)<\/section/i,
      /class="description__text[^"]*"[^>]*>([\s\S]*?)<\/section/i,
      /class="job-description[^"]*"[^>]*>([\s\S]*?)<\/div>/i,
    ];

    for (const regex of selectors) {
      const match = html.match(regex);
      if (match && match[1] && match[1].length > 200) {
        return new NextResponse(match[1].trim(), {
          headers: { "Content-Type": "text/html; charset=utf-8" },
        });
      }
    }

    // Fallback: return the full cached HTML (let the client render it in an iframe or sanitize)
    return new NextResponse(html, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  } catch {
    return NextResponse.json({ error: "not cached" }, { status: 404 });
  }
}
