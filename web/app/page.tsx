"use client";

import { useEffect, useState } from "react";

const RENDER_SVC = process.env.NEXT_PUBLIC_RENDER_SVC ?? "http://localhost:8080";

type GenerateResponse = {
  slug: string;
  mp4_url: string;
  poster_url: string;
  company_name: string;
  domain: string;
  logo_url: string;
  brand_color: string;
  photo_url: string;
  photo_source: string;
  enrichment_source: string;
  plate_key: string;
};

type Plate = {
  key: string;
  label: string;
  css: string;
  text_on_light: boolean;
};

/** The mp4/poster URLs returned by the backend are relative paths in local
 * dev (e.g. `/output/foo.mp4`); resolve them against the FastAPI origin so
 * the browser actually fetches them from there. */
function absolutise(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${RENDER_SVC}${url}`;
}

/** Convert a plain CSS declaration string ("background: #fff; color: red;")
 * into a React inline-style object. The server emits CSS rather than a
 * pre-parsed object so the same string drives both the actual render and
 * the picker thumbnails — single source of truth. */
function parseInlineCss(css: string): React.CSSProperties {
  const out: Record<string, string> = {};
  for (const decl of css.split(";")) {
    const idx = decl.indexOf(":");
    if (idx < 0) continue;
    const prop = decl.slice(0, idx).trim();
    const value = decl.slice(idx + 1).trim();
    if (!prop || !value) continue;
    // kebab-case → camelCase for React style keys.
    const camel = prop.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    out[camel] = value;
  }
  return out as React.CSSProperties;
}

export default function Home() {
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [companyUrl, setCompanyUrl] = useState("");
  const [plates, setPlates] = useState<Plate[]>([]);
  const [selectedPlate, setSelectedPlate] = useState<string>("");

  // QR toggle. Default-on, defaults to Apollo's LinkedIn for this person
  // (handled server-side when qr_url is blank). qrDisabled is the explicit
  // opt-out so the server doesn't fall back to LinkedIn.
  const [qrDisabled, setQrDisabled] = useState(false);
  const [qrUrl, setQrUrl] = useState("");
  const [qrCaption, setQrCaption] = useState("Scan to connect");

  // Banner toggle. Off by default — banner is a marketing/event push, not
  // the everyday case. Whole banner block hidden until enabled.
  const [bannerEnabled, setBannerEnabled] = useState(false);
  const [bannerEvent, setBannerEvent] = useState("");
  const [bannerDates, setBannerDates] = useState("");
  const [bannerLocation, setBannerLocation] = useState("");
  const [bannerCtaText, setBannerCtaText] = useState("LET'S MEET");
  const [bannerCtaUrl, setBannerCtaUrl] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  useEffect(() => {
    // Fetch plate presets once on mount. Failures are silent — the picker
    // just stays empty and the server still falls back to its default plate
    // when we submit with an empty `plate` value.
    let cancelled = false;
    fetch(`${RENDER_SVC}/plates`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list: Plate[]) => {
        if (cancelled) return;
        setPlates(list);
        // Default to the second plate (Soft Studio) rather than the first
        // (pure white), which most users will want to override anyway.
        if (list.length > 0) setSelectedPlate(list[1]?.key ?? list[0].key);
      })
      .catch(() => { /* leave plates empty; server uses its default */ });
    return () => { cancelled = true; };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        full_name: fullName.trim(),
        title: title.trim(),
        company_url: companyUrl.trim(),
        plate: selectedPlate,
        qr_url: qrUrl.trim(),
        qr_caption: qrCaption.trim() || "Scan to connect",
        qr_disabled: qrDisabled,
      };
      if (bannerEnabled && bannerEvent.trim()) {
        body.banner = {
          event_name: bannerEvent.trim(),
          event_dates: bannerDates.trim(),
          event_location: bannerLocation.trim(),
          cta_text: bannerCtaText.trim() || "LET'S MEET",
          cta_url: bannerCtaUrl.trim(),
        };
      }
      const r = await fetch(`${RENDER_SVC}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
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

        {plates.length > 0 && (
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium text-white/80">Background plate</legend>
            <p className="text-xs text-white/40">
              Static surface. Your logo + nametag overlay on top as an animated watermark.
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
              {plates.map((p) => {
                const selected = p.key === selectedPlate;
                return (
                  <button
                    type="button"
                    key={p.key}
                    onClick={() => setSelectedPlate(p.key)}
                    aria-pressed={selected}
                    className={`group flex flex-col gap-1.5 rounded-lg border p-1.5 transition ${
                      selected
                        ? "border-[#055bfb] bg-[#055bfb]/10"
                        : "border-white/15 hover:border-white/30"
                    }`}
                  >
                    {/* Thumbnail: same CSS string the server uses for the
                        actual render, applied to a 16:9 div. Aspect ratio
                        matches the 1920×1080 output. */}
                    <div
                      style={{ ...parseInlineCss(p.css) }}
                      className="aspect-video w-full rounded ring-1 ring-black/20"
                    />
                    <span
                      className={`text-xs ${
                        selected ? "text-white" : "text-white/70"
                      }`}
                    >
                      {p.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}

        {/* QR code panel — default-on with Apollo-LinkedIn auto-fill.
            Compact (one row of inputs) when enabled, hidden when disabled. */}
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium text-white/80">QR code</legend>
          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={!qrDisabled}
              onChange={(e) => setQrDisabled(!e.target.checked)}
              className="h-4 w-4 accent-[#055bfb]"
            />
            <span>
              Show QR code{" "}
              <span className="text-white/40">
                (auto-fills to person&rsquo;s LinkedIn from Apollo if URL is blank)
              </span>
            </span>
          </label>
          {!qrDisabled && !bannerEnabled && (
            <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
              <input
                value={qrUrl}
                onChange={(e) => setQrUrl(e.target.value)}
                placeholder="https://calendly.com/you/intro (or leave blank for LinkedIn)"
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
              <input
                value={qrCaption}
                onChange={(e) => setQrCaption(e.target.value)}
                placeholder="Caption"
                maxLength={40}
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
            </div>
          )}
          {!qrDisabled && bannerEnabled && (
            <p className="text-xs text-white/40">
              Standalone QR is hidden when the banner is on &mdash; the banner carries
              its own CTA QR. Edit the banner&rsquo;s CTA URL instead.
            </p>
          )}
        </fieldset>

        {/* Banner panel — opt-in. Whole block collapsed until enabled. */}
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium text-white/80">Banner</legend>
          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={bannerEnabled}
              onChange={(e) => setBannerEnabled(e.target.checked)}
              className="h-4 w-4 accent-[#055bfb]"
            />
            <span>
              Add a promotional banner along the bottom edge{" "}
              <span className="text-white/40">
                (event push, hiring, campaign &mdash; like the WiseStamp email banner)
              </span>
            </span>
          </label>
          {bannerEnabled && (
            <div className="grid gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-3 sm:grid-cols-2">
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs font-medium text-white/70">Event / message</span>
                <input
                  value={bannerEvent}
                  onChange={(e) => setBannerEvent(e.target.value)}
                  placeholder="Gartner Marketing Symposium"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">Dates</span>
                <input
                  value={bannerDates}
                  onChange={(e) => setBannerDates(e.target.value)}
                  placeholder="June 8–10, 2026"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">Location</span>
                <input
                  value={bannerLocation}
                  onChange={(e) => setBannerLocation(e.target.value)}
                  placeholder="Denver, CO"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">CTA text</span>
                <input
                  value={bannerCtaText}
                  onChange={(e) => setBannerCtaText(e.target.value)}
                  placeholder="LET'S MEET"
                  maxLength={20}
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">CTA URL (→ QR)</span>
                <input
                  value={bannerCtaUrl}
                  onChange={(e) => setBannerCtaUrl(e.target.value)}
                  placeholder="https://calendly.com/you/intro"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
            </div>
          )}
        </fieldset>

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
