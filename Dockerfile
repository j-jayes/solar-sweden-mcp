# Single-stage build — Playwright Chromium must live in the runtime image
# alongside its system library dependencies, so multi-stage is not practical.
# Resulting image is ~1.2 GB; Azure Container Apps supports up to 4 GB.

FROM python:3.12-slim

WORKDIR /app

# System libraries required by Playwright Chromium on Debian slim
# (equivalent to what `playwright install-deps chromium` would add)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright Chromium deps
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    # General utilities
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser to a fixed, known path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy source code and data (includes data/geo/municipalities.geojson if present)
COPY src/ ./src/
COPY data/ ./data/

# Ensure UTF-8 locale for Swedish characters
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
# Add src/ to the Python path so solar_mcp is importable
ENV PYTHONPATH=/app/src

# Expose MCP HTTP port
EXPOSE 8000

# Health check — longer start-period because Playwright init on first call adds latency
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the server
CMD ["uvicorn", "solar_mcp.server:app", "--host", "0.0.0.0", "--port", "8000"]
