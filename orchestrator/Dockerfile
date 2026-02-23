# Phase 3.1 — Cloud Run: single image for API + Worker (tick-driven)
# Build from orchestrator dir:  cd orchestrator && docker build -t orchestrator .
# Run locally:  docker run -p 8080:8080 --env-file .env orchestrator

FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Cloud Run expects PORT=8080; uvicorn default 8000
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
