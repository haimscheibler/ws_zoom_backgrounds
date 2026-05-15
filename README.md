# WiseStamp Interactive Meeting Backgrounds — MVP

Animated, brand-personalized 1920×1080 video backgrounds for Zoom / Teams / Meet.
Same brand engine as `Automated_Email_Signatures`, output format swapped from
HTML/GIF (email) to MP4 video (virtual background).

## Status
MVP — single-user flow: input company URL + name/title → animated MP4 download.
Later phases: directory sync, Zoom Marketplace auto-deploy, calendar-triggered
per-meeting personalization. See sibling folder `ws_Interactive_Zoom_Backgrounds/02_PROJECT_PLAN.md`.

## Enrichment + quality gate
Mirrors `Automated_Email_Signatures` policy: for each request we
  1. Query **Apollo** `/v1/people/match` with `(first_name, last_name, domain)`
     for the person's photo/LinkedIn and the company's logo, color source,
     and socials.
  2. Fall back to **homepage scraping** for any field Apollo didn't supply
     (typically just the logo when Apollo had no org record).
  3. Reject the request with HTTP 422 if neither path yielded a company
     logo **nor** a real profile photo. We won't ship a background built
     from a domain alone.

Set `APOLLO_API_KEY` in `render-svc/.env` — copy from
`Automated_Email_Signatures/.env`. `.env` is gitignored so the secret never
lands in the repo.

## Deploying (Cloud Run)

The render service ships as a Docker image and runs on Cloud Run, mirroring
the booth scanner's deployment model.

```bash
# 1. Build + push the image
gcloud builds submit --config cloudbuild.yaml .

# 2. Deploy to Cloud Run with the Apollo key as an env var
gcloud run deploy render-svc \
  --image gcr.io/$PROJECT_ID/render-svc:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars "APOLLO_API_KEY=$(gcloud secrets versions access latest --secret=apollo-api-key)" \
  --set-env-vars "PUBLIC_BASE_URL=https://render-svc-<hash>-uc.a.run.app"
```

**Apollo key in production.** Store the key in Secret Manager
(`apollo-api-key`) and bind it at deploy time as shown above — never in
the Dockerfile, never in the repo. The service starts up either way: on a
missing key it logs a `WARNING` and falls back to homepage scraping (the
quality gate will reject more renders, but the service still functions for
companies whose homepage has a discoverable logo).

For local dev, `python-dotenv` reads `render-svc/.env`. For CI tests, set
`APOLLO_API_KEY` as a repo secret and inject as a job-level env var; the
on-disk Apollo cache (`render-svc/app/.apollo_cache.json`, gitignored)
keeps repeat lookups free during a test run.

## Layout
```
render-svc/          FastAPI service: brand scrape → HTML → Playwright video → MP4
  app/
    main.py          FastAPI endpoints
    brand_scraper.py Ported from booth_event_scanner (logo + brand color + socials)
    render.py        HTML/CSS animation → headless Chrome video → H.264 MP4 loop
    templates/       Jinja2 1920×1080 background templates
    static/output/   Rendered MP4s served locally (CDN later)
web/                 Next.js frontend: form → preview → download
```

## Local dev

### Backend
```bash
cd render-svc
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8080
```

### Frontend
```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

## Reuse from sibling projects
- `brand_scraper.py` — ported verbatim from `booth_event_scanner/signature-svc/app/`
- Jinja2 template pattern — borrowed from `Automated_Email_Signatures/templates/`
- FastAPI service pattern — mirrors `booth_event_scanner/signature-svc/`

## Zoom virtual background spec
- MP4 / H.264, 1920×1080, 10-second seamless loop, ~3-5 MB
- Subtle ambient motion only — Zoom's matting algorithm breaks on high-contrast
  fast motion (edge artifacts around hair/shoulders)
