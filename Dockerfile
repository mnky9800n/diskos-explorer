# diskosAI web app image. Runs the FastAPI backend behind uvicorn.
# Python 3.12 (stable, wide wheel coverage) rather than 3.14; the web path needs
# no PyMca, and matplotlib/lasio are not required by the current API.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# uv, pinned for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install the project plus the web extra, without dev/test deps.
RUN uv sync --no-dev --extra web

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uv", "run", "--no-dev", "uvicorn", "diskos.web.api:app", "--host", "0.0.0.0", "--port", "8000"]
