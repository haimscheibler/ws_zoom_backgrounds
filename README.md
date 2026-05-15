# WiseStamp Interactive Meeting Backgrounds — MVP

Animated, brand-personalized 1920×1080 video backgrounds for Zoom / Teams / Meet.
Same brand engine as `Automated_Email_Signatures`, output format swapped from
HTML/GIF (email) to MP4 video (virtual background).

## Status
MVP — single-user flow: input company URL + name/title → animated MP4 download.
Later phases: directory sync, Zoom Marketplace auto-deploy, calendar-triggered
per-meeting personalization. See sibling folder `ws_Interactive_Zoom_Backgrounds/02_PROJECT_PLAN.md`.

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
