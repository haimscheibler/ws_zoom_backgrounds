"use client";

import { useEffect, useRef, useState } from "react";

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
  image_attribution?: string;
};

type BrandPreviewData = {
  domain: string;
  company_name: string;
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

/** Live preview of the watermark layout. Renders an inner 1920×1080 div
 * laid out at the exact same positions as `background.html.j2`, wrapped
 * in a scale-transform so the visual size stays small. Animations are
 * disabled — the preview is a static at-a-glance check, not a render. */
function BackgroundPreview({
  fullName,
  title,
  brand,
  plateCss,
  qrEnabled,
  qrCaption,
  bannerEnabled,
  bannerEvent,
  bannerDates,
  bannerLocation,
  bannerCtaText,
  bannerCtaUrl,
}: {
  fullName: string;
  title: string;
  brand: BrandPreviewData | null;
  plateCss: string;
  qrEnabled: boolean;
  qrCaption: string;
  bannerEnabled: boolean;
  bannerEvent: string;
  bannerDates: string;
  bannerLocation: string;
  bannerCtaText: string;
  bannerCtaUrl: string;
}) {
  // Brand color falls back to WiseStamp blue when the live brand-scrape
  // hasn't completed yet — the preview still shows accurate LAYOUT even
  // before the color is known.
  const brandColor = brand?.brand_color || "#055bfb";
  const companyName = brand?.company_name || "Company";
  const logoUrl = brand?.logo_url || "";

  // Banner takes the bottom slot → nametag moves to top-left (mirrors
  // the same logic in render.py). Standalone QR is suppressed when the
  // banner is on (banner brings its own CTA QR).
  const nametagTopLeft = bannerEnabled;
  const showStandaloneQR = qrEnabled && !bannerEnabled;
  const showBanner = bannerEnabled && bannerEvent.trim().length > 0;

  // ResizeObserver-driven scale: cleaner than CSS container queries here
  // because we can't rely on browser support across older Chromium versions
  // in the Playwright recording context, and the math is trivial.
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.4);
  useEffect(() => {
    if (!wrapperRef.current) return;
    const el = wrapperRef.current;
    const update = () => setScale(el.clientWidth / 1920);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={wrapperRef}
      className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/15 bg-black"
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{
          width: 1920,
          height: 1080,
          transform: `scale(${scale})`,
        }}
      >
        {/* Plate */}
        <div
          className="absolute inset-0"
          style={parseInlineCss(plateCss)}
        />

        {/* Brand mark (logo) — only rendered when we have a logo from the
            live brand scrape. The animation pulse is omitted in preview. */}
        {logoUrl && (
          <div
            className="absolute"
            style={{
              top: 110,
              right: 110,
              width: 140,
              height: 140,
              borderRadius: "50%",
              background: "#fff",
              boxShadow: `0 0 0 2px ${brandColor}55, 0 10px 30px rgba(0,0,0,0.28)`,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={logoUrl}
              alt={companyName}
              style={{ maxWidth: 100, maxHeight: 100, objectFit: "contain" }}
            />
          </div>
        )}

        {/* Nametag — bottom-left by default, top-left when banner is on */}
        <div
          className="absolute"
          style={{
            ...(nametagTopLeft
              ? { top: 110, left: 130 }
              : { bottom: 140, left: 130 }),
            maxWidth: 720,
            padding: "24px 36px 24px 32px",
            background: "rgba(10, 22, 38, 0.78)",
            borderLeft: `6px solid ${brandColor}`,
            borderRadius: 12,
            color: "#fff",
            boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
          }}
        >
          <p style={{ fontSize: 44, fontWeight: 700, lineHeight: 1.1, margin: 0, letterSpacing: -0.5 }}>
            {fullName || "Your name"}
          </p>
          {title && (
            <p style={{ fontSize: 22, fontWeight: 400, opacity: 0.85, margin: "6px 0 0" }}>
              {title}
            </p>
          )}
          <p
            style={{
              fontSize: 18,
              fontWeight: 600,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              margin: "14px 0 0",
              paddingTop: 12,
              borderTop: "1px solid rgba(255,255,255,0.18)",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: brandColor,
                marginRight: 10,
                verticalAlign: "middle",
              }}
            />
            {companyName}
          </p>
        </div>

        {/* Standalone QR card */}
        {showStandaloneQR && (
          <div
            className="absolute"
            style={{
              right: 130,
              bottom: 140,
              width: 220,
              padding: "14px 14px 12px",
              background: "#fff",
              borderRadius: 12,
              borderLeft: `6px solid ${brandColor}`,
              boxShadow: "0 12px 40px rgba(0,0,0,0.32)",
              color: "#0a1626",
            }}
          >
            {/* Placeholder QR — the real QR is generated server-side at
                render time. Preview shows a styled square so the user can
                see WHERE the QR will sit, not WHAT it encodes. */}
            <div
              style={{
                width: 192,
                height: 192,
                margin: "0 auto",
                background:
                  "repeating-conic-gradient(#0a1626 0% 25%, transparent 0% 50%) 0/24px 24px",
                opacity: 0.85,
              }}
            />
            <p
              style={{
                margin: "8px 0 0",
                textAlign: "center",
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: 0.4,
                textTransform: "uppercase",
                color: brandColor,
              }}
            >
              {qrCaption || "Scan to connect"}
            </p>
          </div>
        )}

        {/* Banner */}
        {showBanner && (
          <div
            className="absolute"
            style={{
              left: 160,
              right: 160,
              bottom: 50,
              height: 280,
              background: brandColor,
              borderRadius: 16,
              boxShadow: "0 20px 48px rgba(0,0,0,0.4)",
              display: "grid",
              gridTemplateColumns: "1fr 480px",
              alignItems: "center",
              padding: "0 48px",
              color: "#fff",
              overflow: "hidden",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <p
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  letterSpacing: 4,
                  textTransform: "uppercase",
                  opacity: 0.85,
                  margin: 0,
                }}
              >
                MEET ME AT
              </p>
              <p
                style={{
                  fontSize: 56,
                  fontWeight: 800,
                  lineHeight: 1.05,
                  letterSpacing: -1,
                  margin: 0,
                  // 2-line clamp to keep the banner height predictable
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {bannerEvent}
              </p>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                gap: 14,
              }}
            >
              {(bannerDates || bannerLocation) && (
                <p
                  style={{
                    fontSize: 18,
                    fontWeight: 500,
                    opacity: 0.92,
                    textAlign: "right",
                    lineHeight: 1.35,
                    margin: 0,
                  }}
                >
                  {bannerDates}
                  {bannerDates && bannerLocation && <br />}
                  {bannerLocation}
                </p>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                {bannerCtaUrl.trim() && (
                  <div
                    style={{
                      width: 132,
                      height: 132,
                      padding: 10,
                      background: "#fff",
                      borderRadius: 12,
                      boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
                    }}
                  >
                    <div
                      style={{
                        width: "100%",
                        height: "100%",
                        background:
                          "repeating-conic-gradient(#0a1626 0% 25%, transparent 0% 50%) 0/16px 16px",
                        opacity: 0.85,
                      }}
                    />
                  </div>
                )}
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: 64,
                    padding: "0 32px",
                    background: "#fff",
                    color: brandColor,
                    fontSize: 22,
                    fontWeight: 800,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    borderRadius: 999,
                    boxShadow: "0 6px 16px rgba(0,0,0,0.25)",
                  }}
                >
                  {bannerCtaText || "LET'S MEET"}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
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
  const [brandPreview, setBrandPreview] = useState<BrandPreviewData | null>(null);

  // Debounced brand preview: when the user pauses typing in the company URL
  // field, fetch a cheap brand-scrape so the live preview shows real colors
  // and logo. ~500ms server round-trip on a cold domain; cached for repeats.
  useEffect(() => {
    const trimmed = companyUrl.trim();
    if (trimmed.length < 4 || !trimmed.includes(".")) {
      setBrandPreview(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(
          `${RENDER_SVC}/preview-brand?company_url=${encodeURIComponent(trimmed)}`
        );
        if (!r.ok) return;
        const data = (await r.json()) as BrandPreviewData;
        setBrandPreview(data);
      } catch {
        /* preview is non-essential — silently keep showing placeholder */
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [companyUrl]);

  // Resolve the selected plate's CSS for the preview. The "auto" plate's
  // CSS is a striped placeholder anyway (real color isn't known until the
  // server resolves it at render time), so the preview reflects that.
  const selectedPlateCss =
    plates.find((p) => p.key === selectedPlate)?.css ?? "background: #1a2030;";

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

      <section className="mb-6 grid gap-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-white/80">Live preview</p>
          <p className="text-xs text-white/40">
            {brandPreview
              ? `${brandPreview.company_name} · ${brandPreview.brand_color}`
              : "Type a company URL to load real brand colors"}
          </p>
        </div>
        <BackgroundPreview
          fullName={fullName}
          title={title}
          brand={brandPreview}
          plateCss={selectedPlateCss}
          qrEnabled={!qrDisabled}
          qrCaption={qrCaption}
          bannerEnabled={bannerEnabled}
          bannerEvent={bannerEvent}
          bannerDates={bannerDates}
          bannerLocation={bannerLocation}
          bannerCtaText={bannerCtaText}
          bannerCtaUrl={bannerCtaUrl}
        />
      </section>

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
