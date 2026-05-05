FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package and its dependencies
RUN uv pip install --system -e ".[dev]"

# Default: run the API with hot reload (overridden in production)
CMD ["uvicorn", "udc.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
