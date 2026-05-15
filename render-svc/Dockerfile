FROM python:3.12-slim

# System deps for Pillow / lxml + Playwright Chromium runtime libs.
# Playwright's `--with-deps` flag (below) covers most of it, but slim
# images need a couple of basics first.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY render-svc/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install chromium --with-deps

COPY render-svc/app ./app

# Cloud Run injects $PORT; default to 8080 for local docker runs.
ENV PORT=8080
EXPOSE 8080

# APOLLO_API_KEY is provided at deploy time as a Cloud Run env var (or via
# a Secret Manager binding). We deliberately do NOT bake it into the image.
# The app degrades gracefully when it's missing — homepage-scrape fallback
# still produces brand assets for most companies; the quality gate just
# rejects more renders that Apollo would have rescued.

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
