# --- Multi-stage build for a lean production image ---

# Stage 1: Install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools (gcc needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source code and data
COPY src/ ./src/
COPY data/ ./data/

# Ensure UTF-8 locale for Swedish characters
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8

# Expose MCP HTTP port
EXPOSE 8000

# Health check for Azure Container Apps (use curl to avoid httpx import issues)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the server
CMD ["uvicorn", "solar_mcp.server:app", "--host", "0.0.0.0", "--port", "8000"]
