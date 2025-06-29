FROM python:3.13-slim

# Install required packages
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    requests \
    openai \ 
    mailersend \
    python-dotenv \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client \
    google_auth_oauthlib \
    google-cloud \
    google-cloud-vision


WORKDIR /app
COPY . /app

# Expose port
EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]