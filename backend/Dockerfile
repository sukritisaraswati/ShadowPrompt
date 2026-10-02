# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libraries: Pango and HarfBuzz let WeasyPrint render PDF reports;
# fonts give reports readable text. Build tooling is needed for asyncpg wheels
# on some platforms and is removed again so it never reaches the final image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential libpq-dev \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install ".[postgres,pdf,layer3]" \
    && apt-get purge -y build-essential && apt-get autoremove -y

COPY alembic.ini ./
COPY alembic ./alembic

# Run as an unprivileged user. The backend parses hostile HTML and forwards
# requests to third-party endpoints, so it gets no more rights than it needs.
RUN useradd --create-home --uid 10001 shadowprompt \
    && mkdir -p /app/generated_reports \
    && chown -R shadowprompt:shadowprompt /app/generated_reports
USER shadowprompt

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
