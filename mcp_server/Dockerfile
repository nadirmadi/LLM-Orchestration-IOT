FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY mcp_server/requirements.txt /app/mcp_server/requirements.txt
RUN pip install --no-cache-dir -r /app/mcp_server/requirements.txt

# Copy source
COPY database/   /app/database/
COPY mcp_server/ /app/mcp_server/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DB_PATH=/data/monitoring.db
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8765

EXPOSE 8765

CMD ["python", "-m", "mcp_server.server"]
