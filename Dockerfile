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
COPY CampfireValley/requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for MCP server
RUN pip install --no-cache-dir fastapi uvicorn aiohttp websockets pydantic duckduckgo-search redis prometheus-client lz4 httpx

# Optionally install local Campfires source when building with extended context
ARG USE_LOCAL_CAMPFIRES=false
COPY Campfires /opt/campfires-src
RUN if [ "$USE_LOCAL_CAMPFIRES" = "true" ]; then pip install --no-cache-dir /opt/campfires-src; fi

# Copy the application code
COPY CampfireValley /app

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/reports

# Set environment variables
ENV PYTHONPATH=/app
ENV CAMPFIRE_VALLEY_ENV=docker
ENV CAMPFIRE_VALLEY_HOST=0.0.0.0
ENV CAMPFIRE_VALLEY_PORT=8080

# Expose the MCP server port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Create a non-root user for security
RUN useradd -m -u 1000 campfire && \
    chown -R campfire:campfire /app
USER campfire

# Start the web visualization server
CMD ["python", "-m", "campfirevalley.web.server", "--demo", "--host", "0.0.0.0", "--port", "8000"]
