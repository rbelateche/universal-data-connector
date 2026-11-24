# UDC API with the fictional retail demo, as a Hugging Face Docker Space.
# Built by deploy/hf_space.py from a staging folder holding this file,
# pyproject.toml, uv.lock and src/.
FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Spaces run containers as uid 1000
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
    PORT=7860

EXPOSE 7860
CMD ["sh", "-c", "exec .venv/bin/uvicorn udc.api.app:app --host 0.0.0.0 --port ${PORT}"]
