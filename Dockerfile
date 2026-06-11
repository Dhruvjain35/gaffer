# GAFFER — Cloud Run image.
# Python for the ADK agents + Node for the Phoenix MCP server (spawned via npx by the Gaffer).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml

# Pre-fetch the Phoenix MCP server so first coaching session doesn't wait on npx.
RUN npm cache add @arizeai/phoenix-mcp@latest || true

COPY agent ./agent
COPY server ./server
COPY web ./web
COPY data ./data

ENV PORT=8080
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
