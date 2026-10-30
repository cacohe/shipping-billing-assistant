FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

RUN pip install --no-cache-dir uv==0.12.10

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY demo ./demo
COPY tests/fixtures/documents ./tests/fixtures/documents
RUN uv sync --frozen --extra demo --no-dev

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["uv", "run", "--no-sync", "streamlit", "run", "demo/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
