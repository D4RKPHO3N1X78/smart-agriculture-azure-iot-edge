# Multi-stage lightweight Dockerfile for Azure IoT Edge ML Module
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

# Create unprivileged user for secure edge execution
RUN useradd -m -u 1000 moduleuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/moduleuser/.local
ENV PATH=/home/moduleuser/.local/bin:$PATH

# Copy application code, model artifact, and metadata
COPY --chown=moduleuser:moduleuser main.py predictor.py ./
COPY --chown=moduleuser:moduleuser irrigation_model.joblib model_metadata.json ./

USER moduleuser

# Python unbuffered output so logs appear instantly in Azure IoT Edge logs
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-u", "main.py"]
