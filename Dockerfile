FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y wget gnupg2 && \
    apt-get install -y libnss3 libatk-bridge2.0-0 libcups2 libxkbcommon0 libasound2 libgtk-3-0 && \
    pip install --no-cache-dir fastapi uvicorn pydantic playwright && \
    python -m playwright install --with-deps chromium

WORKDIR /app
COPY . /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
