# UDC API with the fictional retail demo, for public hosting (Render, a
# Hugging Face Docker Space...). Build context: the backend/ directory
# (pyproject.toml, uv.lock, src/). The host sets PORT; 8000 otherwise.
FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Run unprivileged (uid 1000 is also what Hugging Face Spaces expect)
RUN useradd -m -u 1000 user
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-editable \
    && chown -R user /app

USER user

# Demo configuration. API_KEY is a Space secret; DATABASE_URL is required by
# the settings but unused by the mapping endpoints.
ENV SEED_DEMO=true \
    DUCKDB_PATH=/tmp/udc-demo.duckdb \
    DATABASE_URL=postgresql://unused@localhost/unused \
    REQUIRE_API_KEY=true \
    PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "exec .venv/bin/uvicorn udc.api.app:app --host 0.0.0.0 --port ${PORT}"]
