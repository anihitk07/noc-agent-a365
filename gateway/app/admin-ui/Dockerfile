# syntax=docker/dockerfile:1

# Build from the gateway/app folder so the admin BFF can also copy config-sync-worker/pricing.py.
# Example: docker build -f admin-ui/Dockerfile gateway/app

# --- stage 1: build the SPA ---
FROM node:20-alpine AS spa
WORKDIR /src/admin-ui/spa
COPY admin-ui/spa/package.json admin-ui/spa/package-lock.json ./
RUN npm ci
COPY admin-ui/spa/ ./
RUN npm run build

# --- stage 2: python runtime serving BFF + built SPA ---
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY admin-ui/bff/requirements.txt ./bff/requirements.txt
RUN pip install --no-cache-dir -r bff/requirements.txt
COPY admin-ui/bff/ ./bff/
COPY config-sync-worker/pricing.py ./config-sync-worker/pricing.py
COPY --from=spa /src/admin-ui/bff/static ./bff/static
EXPOSE 8000
CMD ["uvicorn", "bff.main:app", "--host", "0.0.0.0", "--port", "8000"]
