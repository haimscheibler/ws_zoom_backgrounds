# Architecture — Calendar-triggered Per-Meeting Backgrounds

This doc covers the **Tier 3** vision from `02_PROJECT_PLAN.md` §3:
calendar-driven, per-meeting personalised backgrounds that pre-render
5 minutes before a meeting starts and auto-apply in the user's Zoom client.

The current `main` branch implements Phase 1 (single-user generator). This
document covers Phases 3-4 (Teams/Meet auto-deploy + calendar trigger) at a
design level, with module stubs already in `render-svc/app/calendar/` ready
for the OAuth + API work once external accounts are registered.

---

## Component map

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CALENDAR SOURCES (read-only)                                           │
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐                           │
│  │ Google Calendar  │   │ Microsoft Graph  │                           │
│  │  (OAuth user)    │   │  (OAuth user)    │                           │
│  └────────┬─────────┘   └────────┬─────────┘                           │
│           │                      │                                      │
└───────────┼──────────────────────┼──────────────────────────────────────┘
            │                      │
            ▼                      ▼
        ┌─────────────────────────────────┐
        │  app/calendar/ (this PR)        │
        │  - google.py / microsoft.py     │
        │  - attendees.py — emails →     │
        │    domains → companies          │
        └────────────────┬────────────────┘
                         │
                         ▼  Meeting + attendee[] + start_time
        ┌─────────────────────────────────┐
        │  app/scheduler.py               │
        │                                 │
        │  Every minute:                  │
        │  - find meetings starting in    │
        │    ~5min not yet rendered       │
        │  - dispatch render jobs         │
        │  - mark scheduled               │
        └────────────────┬────────────────┘
                         │
                         ▼  per-meeting render request
        ┌─────────────────────────────────┐
        │  /generate (existing)           │
        │                                 │
        │  Same Apollo + brand-scrape +   │
        │  template + Playwright pipeline │
        │  we already ship. Banner CTA    │
        │  becomes "Welcome, {attendee   │
        │  company} team."                │
        └────────────────┬────────────────┘
                         │
                         ▼  MP4 URL
        ┌─────────────────────────────────┐
        │  app/zoom_app.py                │
        │                                 │
        │  Zoom Marketplace App with      │
        │  virtual-background scope.      │
        │  PUT /users/{userId}/settings/  │
        │       virtual_backgrounds with  │
        │  the rendered MP4.              │
        └─────────────────────────────────┘
```

## Required external accounts and registrations

Everything in `app/calendar/` and `app/zoom_app.py` is a stub today — the
code path is there but raises `NotImplementedError` until you connect real
credentials. **All of these are user-side setup tasks; I can't do them
from inside the codebase.** Order doesn't matter; each is independent.

### 1. Google Calendar (read access)
- Where: https://console.cloud.google.com/
- Steps:
  1. Create a GCP project (or reuse the one hosting Cloud Run)
  2. Enable the **Google Calendar API**
  3. Create OAuth 2.0 client credentials (Application type: Web)
  4. Authorised redirect URIs: `https://render-svc.../oauth/google/callback`
  5. OAuth consent screen: scopes
     `https://www.googleapis.com/auth/calendar.readonly`
- What it returns: `client_id`, `client_secret`, plus an auth URL each user goes through once
- Store in: GCP Secret Manager → injected as `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` env vars

### 2. Microsoft Calendar (read access, for Teams/Outlook users)
- Where: https://portal.azure.com/ → Microsoft Entra ID → App registrations
- Steps:
  1. New registration → name "WiseStamp Meeting Backgrounds"
  2. Supported account types: **Multitenant** (so any org's user can connect)
  3. Redirect URI: `https://render-svc.../oauth/microsoft/callback`
  4. API permissions → Microsoft Graph → Delegated → `Calendars.Read`
  5. Grant admin consent (for your own org during testing)
  6. Certificates & secrets → New client secret
- Stored as: `MICROSOFT_OAUTH_CLIENT_ID` / `_SECRET` / `_TENANT_ID`

### 3. Zoom Marketplace App (virtual background push)
- Where: https://marketplace.zoom.us/
- Steps:
  1. Sign in with a Zoom developer account
  2. Develop → Build App → **OAuth** (Server-to-Server OAuth for our case)
  3. App name: "WiseStamp Meeting Backgrounds"
  4. Scopes: `user:write:settings:virtual_backgrounds`,
     `user:read:user`, `meeting:read:list_meetings`
  5. Submit for review (Zoom approval takes 2-4 weeks the first time;
     internal-only / org-level apps can be self-approved)
- Stored as: `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ZOOM_ACCOUNT_ID`

### 4. Microsoft Teams / Google Meet auto-apply
- Teams: Microsoft has no current programmatic API to auto-apply a virtual
  background to a meeting. Best path today is the **"send to download"** model:
  email/Slack the user a link to the rendered MP4, they import via Teams's
  background picker. Worth re-checking quarterly — Microsoft has been
  promising a Graph extension for a while.
- Meet: similar — Meet doesn't allow programmatic virtual-background changes.
  Same "send to download" fallback.

## Data flow per meeting

For an AE with a 2pm "Acme Corp intro" calendar event:

1. **1:55 pm** — `scheduler.py` finds the upcoming event (5-min lookahead window)
2. **1:55:01** — `attendees.py` parses the event attendees, splits emails into:
   - **Internal** (matches the user's company domain → skipped for personalisation)
   - **External** → typically one or two — these are "the customer"
3. **1:55:02** — Resolve external attendees to a single primary company. Heuristic:
   - If exactly one external attendee, use their domain
   - Otherwise: take the domain shared by the most external attendees
   - Fall back to event title parsing ("Meeting with Acme Corp" → acme.com)
4. **1:55:03** — Call existing `/generate` internally with:
   - The AE's own name/title/company URL (from Zoom user profile)
   - A custom banner: eyebrow="WELCOME", event="Acme Team", cta_url=AE's Calendly
5. **1:55:18** — Render completes (typical 15s end-to-end)
6. **1:55:19** — `zoom_app.py` pushes the MP4 to the AE's Zoom virtual-background slot via
   `POST /users/{user_id}/settings/virtual_backgrounds`
7. **2:00 pm** — AE joins meeting with personalised background already active

## What this PR ships (versus full Tier 3)

- ✅ Architecture documented (this file)
- ✅ Stub modules with clear `TODO` markers where API calls go
- ✅ Setup checklist for the four external accounts
- ❌ OAuth flows — need the registered client IDs first
- ❌ Scheduler loop — needs persistent storage (Firestore / Cloud Tasks)
- ❌ Zoom Marketplace app — needs Zoom developer registration + review

When the external accounts are ready, the stubs become real over ~1-2 weeks
of implementation work (per the project plan's Phase 4 estimate). Most of
the heavy lifting — brand scraping, Apollo enrichment, rendering — is
already done; this phase is mostly OAuth plumbing + a scheduling loop.

## Privacy and CISO notes

Reading calendar events means we see external attendee emails and event
titles. The CISO sign-off this needs (per the project plan §7) is around:

- **Calendar data residency** — events stay in-memory during render, are
  not persisted by `render-svc`. Only the rendered MP4 lands in GCS, and
  it doesn't contain attendee PII (only the AE's own name and the company
  logo of the meeting target).
- **OAuth token scope** — `calendar.readonly` is the smallest scope that
  works. We never write to calendars.
- **External attendee notification** — viewers of an AE's video call see
  the personalised background but never the data we used to compute it.
  This is materially the same disclosure surface as the AE manually
  building a background — but happening at scale and on a schedule.
