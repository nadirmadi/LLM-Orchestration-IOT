FROM python:3.12-slim

WORKDIR /app

# System deps for building some Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps. We install database + crew + scripts deps here
# because the same container is used to run any of the test scripts.
COPY mcp_server/requirements.txt /app/mcp_server/requirements.txt
COPY crew/requirements.txt        /app/crew/requirements.txt
RUN pip install --no-cache-dir \
      -r /app/mcp_server/requirements.txt \
      -r /app/crew/requirements.txt \
      fastapi uvicorn

# Copy source
COPY database/   /app/database/
COPY mcp_server/ /app/mcp_server/
COPY crew/       /app/crew/
COPY scripts/    /app/scripts/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
