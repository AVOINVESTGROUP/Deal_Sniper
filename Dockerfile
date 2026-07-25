FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall --yes setuptools wheel

COPY main.py ./
COPY src ./src

ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision=$GIT_COMMIT

RUN mkdir -p /app/data && chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

ENTRYPOINT []
CMD ["uvicorn", "src.web:app", "--host", "0.0.0.0", "--port", "8080"]
