# ---------Build Next.js frontend ----------
FROM node:22-alpine AS frontend-builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Public Clerk key for Next.js build
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

RUN npm run build


# ----------Run FastAPI backend ----------
FROM python:3.12-slim

WORKDIR /app

# Copy Python dependencies
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI app
COPY api ./api

# Copy the built Next.js frontend
COPY --from=frontend-builder /app/out ./static

# Optional: healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

# Start FastAPI ( app is in api/index.py)
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]
