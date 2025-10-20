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
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for MCP server
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    aiohttp \
    websockets \
    pydantic \
    duckduckgo-search \
    redis \
    prometheus-client \
    lz4

# Copy the application code
COPY . .

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

# Start the development team MCP server
CMD ["python", "development_team_server.py"]