FROM python:3.13-slim

# Install required packages
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    requests \
    openai \
    python-multipart \
    google-auth \
    google-api-python-client


WORKDIR /app
COPY . /app

# Expose port
EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]