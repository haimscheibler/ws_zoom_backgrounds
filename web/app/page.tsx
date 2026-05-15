"use client";

import { useState } from "react";

const RENDER_SVC = process.env.NEXT_PUBLIC_RENDER_SVC ?? "http://localhost:8080";

type GenerateResponse = {
  slug: string;
  mp4_url: string;
  poster_url: string;
  company_name: string;
  domain: string;
  logo_url: string;
  brand_color: string;
};

/** The mp4/poster URLs returned by the backend are relative paths in local
 * dev (e.g. `/output/foo.mp4`); resolve them against the FastAPI origin so
 * the browser actually fetches them from there. */
function absolutise(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${RENDER_SVC}${url}`;
}

export default function Home() {
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [companyUrl, setCompanyUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const r = await fetch(`${RENDER_SVC}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName.trim(),
          title: title.trim(),
          company_url: companyUrl.trim(),
        }),
      });
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || `HTTP ${r.status}`);
      }
      const data = (await r.json()) as GenerateResponse;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Render failed");
    } finally {
      setSubmitting(false);
    }
  }

  const mp4 = result ? absolutise(result.mp4_url) : null;
  const poster = result ? absolutise(result.poster_url) : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-12">
      <header className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight">
          Interactive Meeting Backgrounds
          <span className="ml-2 rounded bg-white/10 px-2 py-0.5 text-xs font-medium uppercase text-white/70">
            MVP
          </span>
        </h1>
        <p className="mt-2 text-white/60">
          Drop your name, title, and company URL — get an animated, brand-personalised
          1920×1080 MP4 you can drop straight into Zoom.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="grid gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      >
        <label className="grid gap-1.5">
          <span className="text-sm font-medium text-white/80">Full name</span>
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jane Cooper"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 outline-none focus:border-white/40"
          />
        </label>

        <label className="grid gap-1.5">
          <span className="text-sm font-medium text-white/80">
            Title <span className="text-white/40">(optional)</span>
          </span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Head of Marketing"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 outline-none focus:border-white/40"
          />
        </label>

        <label className="grid gap-1.5">
          <span className="text-sm font-medium text-white/80">Company URL</span>
          <input
            required
            value={companyUrl}
            onChange={(e) => setCompanyUrl(e.target.value)}
            placeholder="wisestamp.com"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 outline-none focus:border-white/40"
          />
          <span className="text-xs text-white/40">
            We scrape the homepage for the company logo and dominant brand color.
          </span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="mt-2 rounded-lg bg-[#055bfb] px-4 py-2.5 font-semibold text-white transition hover:bg-[#0468ff] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Rendering… (~15s)" : "Generate background"}
        </button>

        {error && (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        )}
      </form>

      {result && mp4 && poster && (
        <section className="mt-10 grid gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-white/60">Preview</p>
              <p className="text-lg font-medium">
                {result.company_name}{" "}
                <span
                  className="ml-2 inline-block h-3 w-3 translate-y-[1px] rounded-full"
                  style={{ background: result.brand_color }}
                  title={result.brand_color}
                />
                <span className="ml-1 text-xs text-white/40">{result.brand_color}</span>
              </p>
            </div>
            <a
              href={mp4}
              download={`${result.slug}.mp4`}
              className="rounded-lg bg-white px-4 py-2 font-semibold text-[#0a1626] transition hover:bg-white/90"
            >
              Download MP4
            </a>
          </div>

          <video
            key={mp4}
            src={mp4}
            poster={poster}
            autoPlay
            loop
            muted
            playsInline
            className="aspect-video w-full rounded-xl border border-white/10 bg-black"
          />

          <details className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-white/70">
            <summary className="cursor-pointer font-medium text-white/80">
              How to use in Zoom
            </summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              <li>Click <strong>Download MP4</strong> above.</li>
              <li>In Zoom: Settings → Backgrounds &amp; Effects → <strong>+</strong> → Add Video.</li>
              <li>Pick the downloaded file. Zoom loops it automatically.</li>
            </ol>
          </details>
        </section>
      )}
    </main>
  );
}
