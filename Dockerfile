# CampfireValley Development Team Docker Image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for MCP server
RUN pip install --no-cache-dir fastapi uvicorn aiohttp websockets pydantic duckduckgo-search redis prometheus-client lz4 httpx

ARG USE_GIT_CAMPFIRES=true
RUN if [ "$USE_GIT_CAMPFIRES" = "true" ]; then pip install --no-cache-dir "campfires @ git+https://github.com/mikehibbert/pyCampfires.git@v0.4.3"; fi

# Copy the application code (entire repo)
COPY . /app

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/reports

# Set environment variables
ENV PYTHONPATH=/app
ENV CAMPFIRE_VALLEY_ENV=docker
ENV CAMPFIRE_VALLEY_HOST=0.0.0.0
ENV CAMPFIRE_VALLEY_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Create a non-root user for security
RUN useradd -m -u 1000 campfire && \
    chown -R campfire:campfire /app
USER campfire

# Start the web visualization server
CMD ["python", "-m", "campfirevalley.web.server", "--demo", "--host", "0.0.0.0", "--port", "8000"]
