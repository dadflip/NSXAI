FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for owlready2 and HermiT
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY hermit_api_server.py .

EXPOSE 7777

# Set environment variables
ENV FUSEKI_URL=http://localhost:3030
ENV FUSEKI_DATASET=GaTO
ENV ONTOLOGY_DIR=/ontologies
ENV PYTHONUNBUFFERED=1

CMD ["python", "hermit_api_server.py"]
