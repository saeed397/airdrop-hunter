# Airdrop Hunter – production image for Render free tier
FROM python:3.12-slim

# Prevent Python from writing .pyc and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# System deps (needed by psycopg2, lxml, whois)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    whois \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Render sets $PORT; default 10000 for local docker run
ENV PORT=10000
EXPOSE 10000

# Healthcheck for local/docker (Render uses its own)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health')" || exit 1

# Start uvicorn (single worker – enough for free tier + scheduler)
CMD uvicorn src.server:app --host 0.0.0.0 --port ${PORT} --workers 1
