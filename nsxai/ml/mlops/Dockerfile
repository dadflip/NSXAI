FROM python:3.11-slim

WORKDIR /api

# Dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app/ ./app/

# Artifacts directory (mounted at runtime OR baked in)
RUN mkdir -p ./artifacts

# Non-root user for security
RUN useradd -m apiuser && chown -R apiuser /api
USER apiuser

EXPOSE 8000

ENV ARTIFACTS_DIR=/api/artifacts

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
