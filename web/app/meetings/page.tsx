"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const RENDER_SVC = process.env.NEXT_PUBLIC_RENDER_SVC ?? "http://localhost:8080";

type Attendee = {
  email: string;
  name?: string;
  company?: string;
};

type Meeting = {
  id: string;
  title: string;
  start_time: number;
  duration_minutes: number;
  attendees: Attendee[];
  welcome_template: string;
  plate: string;
  render_status: "idle" | "rendering" | "ready" | "failed";
  rendered_at: number;
  rendered_mp4_url: string;
  rendered_poster_url: string;
  primary_company_name: string;
  primary_domain: string;
  last_render_error: string;
  created_at: number;
  updated_at: number;
};

type AEProfile = {
  full_name: string;
  title: string;
  company_url: string;
  qr_url: string;
};

const AE_LOCAL_STORAGE_KEY = "wisestamp.ae-profile.v1";
const DEFAULT_AE: AEProfile = {
  full_name: "",
  title: "",
  company_url: "",
  qr_url: "",
};

// ── Helpers ────────────────────────────────────────────────────────────────

function absolutise(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${RENDER_SVC}${url}`;
}

/** "in 4 min" / "in 2h 15m" / "now" / "12 min ago" — relative timing
 * that re-evaluates as the user keeps the page open. Returns absolute date
 * for anything more than 12h away to avoid useless "in 16h 23m" strings. */
function relativeTime(start_time: number, nowMs: number): { text: string; bucket: "past" | "active" | "soon" | "later" | "tomorrow" } {
  const diffMs = start_time * 1000 - nowMs;
  const absMin = Math.round(Math.abs(diffMs) / 60_000);
  if (diffMs < -60_000) {
    // ended already
    return { text: `${absMin} min ago`, bucket: "past" };
  }
  if (Math.abs(diffMs) < 60_000) {
    return { text: "starting now", bucket: "active" };
  }
  if (diffMs < 5 * 60_000) {
    return { text: `in ${absMin} min`, bucket: "active" };
  }
  if (diffMs < 60 * 60_000) {
    return { text: `in ${absMin} min`, bucket: "soon" };
  }
  if (diffMs < 12 * 60 * 60_000) {
    const h = Math.floor(absMin / 60);
    const m = absMin % 60;
    return { text: m ? `in ${h}h ${m}m` : `in ${h}h`, bucket: "later" };
  }
  const d = new Date(start_time * 1000);
  return {
    text: d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }),
    bucket: "tomorrow",
  };
}

function attendeeInitials(a: Attendee): string {
  if (a.name) {
    return a.name.split(" ").filter(Boolean).slice(0, 2).map((s) => s[0]!.toUpperCase()).join("");
  }
  const local = a.email.split("@")[0] ?? "";
  return (local[0] ?? "?").toUpperCase();
}

function attendeeDomain(a: Attendee): string {
  const at = a.email.indexOf("@");
  return at >= 0 ? a.email.slice(at + 1) : "";
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ae, setAe] = useState<AEProfile>(DEFAULT_AE);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  // Per-meeting render state — independent of the meeting record so the
  // spinner shows immediately when the user clicks, even before the
  // server's render_status flips.
  const [renderingIds, setRenderingIds] = useState<Set<string>>(new Set());

  // Inline create-meeting form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newStart, setNewStart] = useState(() => {
    // Default: 30 min from now, rounded to next 5-min mark — feels current
    // in the demo without being literally "now."
    const d = new Date(Date.now() + 30 * 60_000);
    d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
    return d.toISOString().slice(0, 16);  // datetime-local format
  });
  const [newDuration, setNewDuration] = useState(30);
  const [newAttendeesRaw, setNewAttendeesRaw] = useState("");
  const [newWelcome, setNewWelcome] = useState("Welcome, {company} team! 👋");

  // Load AE profile from localStorage on mount.
  useEffect(() => {
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem(AE_LOCAL_STORAGE_KEY) : null;
      if (raw) setAe({ ...DEFAULT_AE, ...JSON.parse(raw) });
    } catch { /* corrupt localStorage — just use defaults */ }
  }, []);

  // Persist AE profile changes back to localStorage.
  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        localStorage.setItem(AE_LOCAL_STORAGE_KEY, JSON.stringify(ae));
      }
    } catch { /* private mode etc. — preview only */ }
  }, [ae]);

  // Re-evaluate relative timestamps every 30s so the "next up" highlight
  // stays accurate without a full page reload.
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const reload = useCallback(async () => {
    try {
      const r = await fetch(`${RENDER_SVC}/meetings`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMeetings((await r.json()) as Meeting[]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load meetings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function seedDemo() {
    try {
      const r = await fetch(`${RENDER_SVC}/meetings/seed`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMeetings((await r.json()) as Meeting[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Seed failed");
    }
  }

  async function renderMeeting(m: Meeting) {
    if (!ae.full_name.trim() || !ae.company_url.trim()) {
      setError("Fill in your name and company URL above first.");
      return;
    }
    setRenderingIds((prev) => new Set(prev).add(m.id));
    setError(null);
    try {
      const r = await fetch(`${RENDER_SVC}/meetings/${m.id}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ae),
      });
      if (!r.ok) {
        const text = await r.text();
        throw new Error(text);
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Render failed");
    } finally {
      setRenderingIds((prev) => {
        const s = new Set(prev);
        s.delete(m.id);
        return s;
      });
    }
  }

  async function deleteMeeting(m: Meeting) {
    if (!confirm(`Delete "${m.title}"?`)) return;
    try {
      const r = await fetch(`${RENDER_SVC}/meetings/${m.id}`, { method: "DELETE" });
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function addMeeting() {
    try {
      const startTimeUnix = Math.floor(new Date(newStart).getTime() / 1000);
      const attendees = newAttendeesRaw
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((entry) => {
          // Allow "Name <email@domain>" or just "email@domain"
          const m = entry.match(/^(.*?)\s*<([^>]+@[^>]+)>\s*$/);
          if (m) return { name: m[1].trim(), email: m[2].trim() };
          return { email: entry };
        });
      const r = await fetch(`${RENDER_SVC}/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTitle.trim(),
          start_time: startTimeUnix,
          duration_minutes: newDuration,
          attendees,
          welcome_template: newWelcome.trim() || "Welcome, {company} team!",
          plate: "office_studio",
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setShowAddForm(false);
      setNewTitle("");
      setNewAttendeesRaw("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  }

  // The "next up" meeting: the soonest one whose start hasn't passed yet.
  // (Currently-in-progress meetings get a different treatment — they're not
  // "next up" since they're already happening, but they're not "past" either.)
  const nextUpId = meetings.find((m) => m.start_time * 1000 > nowMs - 60_000)?.id;

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-12">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-white/40">
            <Link href="/" className="hover:text-white/60">← Back to generator</Link>
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            Meetings today
          </h1>
          <p className="mt-2 text-white/60">
            Each meeting auto-renders a personalised background using
            the attendees&apos; companies. Click <strong>Prepare background</strong>{" "}
            to render now; on a real deployment the calendar trigger would
            do this 5 min before each meeting.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            type="button"
            onClick={seedDemo}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-sm hover:border-white/30"
            title="Replace the meeting list with a fresh batch of demo meetings centred on now"
          >
            Reset demo data
          </button>
          <button
            type="button"
            onClick={() => setShowAddForm((v) => !v)}
            className="rounded-lg bg-[#055bfb] px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-[#0468ff]"
          >
            {showAddForm ? "Cancel" : "+ Add meeting"}
          </button>
        </div>
      </header>

      {/* AE profile — pinned at the top, persisted in localStorage. Every
          meeting render uses this as the "you" context. */}
      <section className="mb-6 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <p className="mb-2 text-sm font-medium text-white/80">Your profile</p>
        <p className="mb-3 text-xs text-white/40">
          Used as the AE&apos;s name + branding in every meeting render. Saved in your browser only.
        </p>
        <div className="grid gap-2 sm:grid-cols-4">
          <input
            value={ae.full_name}
            onChange={(e) => setAe({ ...ae, full_name: e.target.value })}
            placeholder="Your full name"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
          />
          <input
            value={ae.title}
            onChange={(e) => setAe({ ...ae, title: e.target.value })}
            placeholder="Your title"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
          />
          <input
            value={ae.company_url}
            onChange={(e) => setAe({ ...ae, company_url: e.target.value })}
            placeholder="yourcompany.com"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
          />
          <input
            value={ae.qr_url}
            onChange={(e) => setAe({ ...ae, qr_url: e.target.value })}
            placeholder="Your LinkedIn / Calendly URL"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
          />
        </div>
      </section>

      {/* Inline create form */}
      {showAddForm && (
        <section className="mb-6 grid gap-3 rounded-2xl border border-white/15 bg-white/[0.03] p-4">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Meeting title — e.g., Acme Corp / WiseStamp intro"
            className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="grid gap-1">
              <span className="text-xs text-white/60">Start time</span>
              <input
                type="datetime-local"
                value={newStart}
                onChange={(e) => setNewStart(e.target.value)}
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs text-white/60">Duration (minutes)</span>
              <input
                type="number"
                min={5}
                max={480}
                step={5}
                value={newDuration}
                onChange={(e) => setNewDuration(Number(e.target.value))}
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
            </label>
          </div>
          <label className="grid gap-1">
            <span className="text-xs text-white/60">
              Attendees{" "}
              <span className="text-white/40">
                — comma- or newline-separated. Use{" "}
                <code className="text-white/60">Name &lt;email@domain&gt;</code>{" "}
                or just the email.
              </span>
            </span>
            <textarea
              value={newAttendeesRaw}
              onChange={(e) => setNewAttendeesRaw(e.target.value)}
              placeholder={"Patrick Collison <patrick@stripe.com>\njohn@stripe.com"}
              className="min-h-[80px] rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-white/60">
              Welcome template{" "}
              <span className="text-white/40">
                — <code>{"{company}"}</code> is replaced with the resolved attendee company
              </span>
            </span>
            <input
              value={newWelcome}
              onChange={(e) => setNewWelcome(e.target.value)}
              placeholder="Welcome, {company} team! 👋"
              className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
            />
          </label>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm hover:border-white/30"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={addMeeting}
              disabled={!newTitle.trim()}
              className="rounded-lg bg-[#055bfb] px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-[#0468ff] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Create meeting
            </button>
          </div>
        </section>
      )}

      {error && (
        <p className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading && <p className="text-white/50">Loading…</p>}

      {!loading && meetings.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-center">
          <p className="text-white/70">No meetings yet.</p>
          <p className="mt-1 text-sm text-white/40">
            Click <strong>Reset demo data</strong> to seed a few example meetings
            against real companies, or <strong>Add meeting</strong> to create one
            yourself.
          </p>
        </div>
      )}

      <ul className="grid gap-3">
        {meetings.map((m) => {
          const isNext = m.id === nextUpId;
          const rel = relativeTime(m.start_time, nowMs);
          const isRendering = renderingIds.has(m.id) || m.render_status === "rendering";
          const isReady = m.render_status === "ready" && !!m.rendered_mp4_url;
          const isPast = rel.bucket === "past";

          return (
            <li
              key={m.id}
              className={`relative rounded-xl border bg-white/[0.03] p-5 ${
                isNext
                  ? "border-[#055bfb] shadow-[0_0_0_1px_rgba(5,91,251,0.45)]"
                  : isPast
                    ? "border-white/10 opacity-60"
                    : "border-white/15"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1">
                  {isNext && (
                    <p className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-[#055bfb]/20 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-[#7ea4ff]">
                      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#7ea4ff]" />
                      Next up
                    </p>
                  )}
                  <h3 className="text-lg font-semibold">{m.title}</h3>
                  <p className={`mt-0.5 text-sm ${rel.bucket === "active" ? "text-emerald-300" : "text-white/60"}`}>
                    {rel.text}{" "}
                    <span className="text-white/40">· {m.duration_minutes} min</span>
                  </p>

                  {m.attendees.length > 0 && (
                    <ul className="mt-3 flex flex-wrap items-center gap-2">
                      {m.attendees.map((a, idx) => (
                        <li
                          key={`${m.id}-${idx}`}
                          className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-2 py-1 text-xs"
                          title={a.email}
                        >
                          <span className="grid h-5 w-5 place-items-center rounded-full bg-[#055bfb]/30 text-[10px] font-semibold">
                            {attendeeInitials(a)}
                          </span>
                          <span className="text-white/85">
                            {a.name || a.email.split("@")[0]}
                          </span>
                          <span className="text-white/40">@{attendeeDomain(a)}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {m.primary_company_name && (
                    <p className="mt-2 text-xs text-white/50">
                      Auto-detected company → <strong className="text-white/80">{m.primary_company_name}</strong>
                    </p>
                  )}
                  {m.last_render_error && (
                    <p className="mt-2 text-xs text-red-300/90">
                      {m.last_render_error}
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2">
                  {isReady ? (
                    <>
                      <a
                        href={absolutise(m.rendered_mp4_url)}
                        download={`${m.title.replace(/[^a-z0-9]+/gi, "_")}.mp4`}
                        className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-[#0a1626] hover:bg-white/90"
                      >
                        Download MP4
                      </a>
                      <button
                        type="button"
                        onClick={() => renderMeeting(m)}
                        className="text-xs text-white/50 hover:text-white/80"
                      >
                        Re-render
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => renderMeeting(m)}
                      disabled={isRendering || isPast}
                      className="rounded-lg bg-[#055bfb] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0468ff] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isRendering ? "Rendering…" : isPast ? "Ended" : "Prepare background"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => deleteMeeting(m)}
                    className="text-xs text-white/40 hover:text-red-300"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {isReady && m.rendered_poster_url && (
                <div className="mt-4 overflow-hidden rounded-lg border border-white/10">
                  <video
                    src={absolutise(m.rendered_mp4_url)}
                    poster={absolutise(m.rendered_poster_url)}
                    autoPlay
                    loop
                    muted
                    playsInline
                    className="block aspect-video w-full bg-black"
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </main>
  );
}
