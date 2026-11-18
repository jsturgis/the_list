# The page fetcher for the Ingest jobs workflow, run on the home server (ADR 0007, scraper/README.md).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && patchright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY scraper.py .

# Runs as the apps user TrueNAS gives its apps (568); the browser profile (cookies) lives in /data.
RUN groupadd -g 568 apps && useradd -u 568 -g apps -m scraper && mkdir -p /data && chown scraper:apps /data
USER scraper

EXPOSE 8790
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8790/health')"
CMD ["uvicorn", "scraper:app", "--host", "0.0.0.0", "--port", "8790"]
