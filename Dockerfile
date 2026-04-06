FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    HOME=/home/app \
    APP_HOME=/opt/send-me-research

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libcairo2 \
    libffi-dev \
    libfontconfig1 \
    libgdk-pixbuf-2.0-0 \
    libharfbuzz-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    nodejs \
    npm \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex

WORKDIR /opt/send-me-research

COPY pyproject.toml uv.lock .python-version README.md /opt/send-me-research/
COPY src /opt/send-me-research/src
COPY templates /opt/send-me-research/templates

RUN uv sync --frozen --no-dev

ENV PATH="/opt/send-me-research/.venv/bin:$PATH"

WORKDIR /workspace

CMD ["uv", "run", "send-me-research", "--help"]
