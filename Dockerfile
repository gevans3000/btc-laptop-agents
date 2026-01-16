# Multi-stage build for lightweight runner
FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY config/ config/
COPY pyproject.toml .

# Install package
RUN pip install -e .

# Create non-root user
RUN useradd -m trader
RUN mkdir -p logs runs && chown trader:trader logs runs
USER trader

# Default command
CMD ["la", "run", "--mode", "live-session", "--async", "--duration", "10"]
