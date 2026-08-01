FROM python:3.11.15-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /build

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --prefix=/runtime -r requirements.txt

FROM python:3.11.15-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY --from=builder /runtime/lib/python3.11/site-packages/ \
    /usr/local/lib/python3.11/site-packages/

RUN rm -rf \
        /usr/local/bin/pip* \
        /usr/local/lib/python3.11/ensurepip \
        /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/wheel* \
    && python -c "import importlib.util; names = ('pip', 'setuptools', 'wheel'); assert not [name for name in names if importlib.util.find_spec(name)]"

COPY main.py ./
COPY src ./src
COPY scripts ./scripts

ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision=$GIT_COMMIT

RUN mkdir -p /app/data && chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "src.web:app", "--host", "0.0.0.0", "--port", "8080"]
