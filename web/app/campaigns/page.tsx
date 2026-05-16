"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const RENDER_SVC = process.env.NEXT_PUBLIC_RENDER_SVC ?? "http://localhost:8080";

type BannerConfig = {
  event_name: string;
  event_dates: string;
  event_location: string;
  eyebrow: string;
  cta_text: string;
  cta_url: string;
};

type Campaign = {
  id: string;
  name: string;
  banner: BannerConfig;
  created_at: number;
  updated_at: number;
  expires_at: string;
};

const emptyBanner: BannerConfig = {
  event_name: "",
  event_dates: "",
  event_location: "",
  eyebrow: "MEET ME AT",
  cta_text: "LET'S MEET",
  cta_url: "",
};

function fmtDate(unix: number): string {
  if (!unix) return "—";
  return new Date(unix * 1000).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function isExpired(expires_at: string): boolean {
  if (!expires_at) return false;
  return new Date(expires_at).getTime() < Date.now();
}

export default function CampaignsPage() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editor state. `editingId` empty means "creating new". The form is the
  // same fields either way — keeps the admin UI to one component.
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [formName, setFormName] = useState("");
  const [formBanner, setFormBanner] = useState<BannerConfig>(emptyBanner);
  const [formExpires, setFormExpires] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      setLoading(true);
      const r = await fetch(`${RENDER_SVC}/campaigns`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setItems((await r.json()) as Campaign[]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openNew() {
    setEditingId("");
    setFormName("");
    setFormBanner(emptyBanner);
    setFormExpires("");
    setEditorOpen(true);
  }

  function openEdit(c: Campaign) {
    setEditingId(c.id);
    setFormName(c.name);
    setFormBanner(c.banner);
    setFormExpires(c.expires_at);
    setEditorOpen(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const url = editingId
        ? `${RENDER_SVC}/campaigns/${editingId}`
        : `${RENDER_SVC}/campaigns`;
      const r = await fetch(url, {
        method: editingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formName.trim(),
          banner: formBanner,
          expires_at: formExpires.trim(),
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setEditorOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(c: Campaign) {
    if (!confirm(`Delete campaign "${c.name}"?`)) return;
    try {
      const r = await fetch(`${RENDER_SVC}/campaigns/${c.id}`, { method: "DELETE" });
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-12">
      <header className="mb-8 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-white/40">
            <Link href="/" className="hover:text-white/60">
              ← Back to generator
            </Link>
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            Banner campaigns
          </h1>
          <p className="mt-2 text-white/60">
            Saved banner presets. Pick one in the generator instead of typing
            event details every time.
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="rounded-lg bg-[#055bfb] px-4 py-2.5 font-semibold text-white transition hover:bg-[#0468ff]"
        >
          + New campaign
        </button>
      </header>

      {error && (
        <p className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading && <p className="text-white/50">Loading…</p>}

      {!loading && items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-center">
          <p className="text-white/70">No campaigns yet.</p>
          <p className="mt-1 text-sm text-white/40">
            Create one to reuse banner content across multiple renders.
          </p>
        </div>
      )}

      <div className="grid gap-3">
        {items.map((c) => {
          const expired = isExpired(c.expires_at);
          return (
            <article
              key={c.id}
              className={`rounded-xl border border-white/10 bg-white/[0.03] p-5 ${
                expired ? "opacity-60" : ""
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold">
                    {c.name}{" "}
                    {expired && (
                      <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-xs font-medium text-amber-300">
                        EXPIRED
                      </span>
                    )}
                  </h3>
                  <p className="mt-1 text-sm text-white/70">
                    <span className="text-white/40">{c.banner.eyebrow}</span>{" "}
                    {c.banner.event_name}
                  </p>
                  <p className="mt-0.5 text-xs text-white/40">
                    {c.banner.event_dates}
                    {c.banner.event_dates && c.banner.event_location && " · "}
                    {c.banner.event_location}
                    {c.banner.cta_url && (
                      <>
                        {" · "}CTA → {c.banner.cta_url.slice(0, 60)}
                      </>
                    )}
                  </p>
                  <p className="mt-2 text-xs text-white/40">
                    Created {fmtDate(c.created_at)}
                    {c.expires_at && ` · Expires ${c.expires_at}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(c)}
                    className="rounded-md border border-white/15 px-3 py-1.5 text-sm hover:border-white/30"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(c)}
                    className="rounded-md border border-red-500/30 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/10"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {editorOpen && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/70 p-4">
          <div className="grid w-full max-w-2xl gap-3 rounded-2xl border border-white/15 bg-[#0a1626] p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">
                {editingId ? "Edit campaign" : "New campaign"}
              </h2>
              <button
                type="button"
                onClick={() => setEditorOpen(false)}
                className="text-white/50 hover:text-white"
              >
                ✕
              </button>
            </div>

            <label className="grid gap-1">
              <span className="text-xs font-medium text-white/70">Campaign label</span>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Q2 Gartner Push"
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
            </label>

            <div className="grid gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-3 sm:grid-cols-2">
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs font-medium text-white/70">Event / message</span>
                <input
                  value={formBanner.event_name}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, event_name: e.target.value })
                  }
                  placeholder="Gartner Marketing Symposium"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">Dates</span>
                <input
                  value={formBanner.event_dates}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, event_dates: e.target.value })
                  }
                  placeholder="June 8–10, 2026"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">Location</span>
                <input
                  value={formBanner.event_location}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, event_location: e.target.value })
                  }
                  placeholder="Denver, CO"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">Eyebrow</span>
                <input
                  value={formBanner.eyebrow}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, eyebrow: e.target.value })
                  }
                  placeholder="MEET ME AT"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium text-white/70">CTA text</span>
                <input
                  value={formBanner.cta_text}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, cta_text: e.target.value })
                  }
                  placeholder="LET'S MEET"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs font-medium text-white/70">CTA URL (→ QR)</span>
                <input
                  value={formBanner.cta_url}
                  onChange={(e) =>
                    setFormBanner({ ...formBanner, cta_url: e.target.value })
                  }
                  placeholder="https://calendly.com/team/intro"
                  className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
                />
              </label>
            </div>

            <label className="grid gap-1">
              <span className="text-xs font-medium text-white/70">
                Expires on{" "}
                <span className="text-white/40">(YYYY-MM-DD, optional)</span>
              </span>
              <input
                value={formExpires}
                onChange={(e) => setFormExpires(e.target.value)}
                placeholder="2026-06-11"
                className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-white/40"
              />
            </label>

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditorOpen(false)}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm hover:border-white/30"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={!formName.trim() || !formBanner.event_name.trim() || saving}
                className="rounded-lg bg-[#055bfb] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0468ff] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving…" : editingId ? "Save changes" : "Create campaign"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
