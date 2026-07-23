FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY src ./src

RUN mkdir -p /app/data && chown -R app:app /app
USER app

ENTRYPOINT ["python", "main.py"]
CMD ["bot"]
