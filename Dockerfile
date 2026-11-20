FROM python:3.11-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY . .
# Railway sets PORT
CMD ["sh", "-c", "uv run --no-dev uvicorn agent.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
