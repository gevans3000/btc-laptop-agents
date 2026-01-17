# Multi-stage build for lightweight runner
FROM python:3.11-slim AS base

WORKDIR /app

# Copy source and definitions
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

# Install package and dependencies
RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd -m trader
RUN mkdir -p logs runs && chown trader:trader logs runs
USER trader

# Default command
CMD ["la", "run", "--mode", "live-session", "--async", "--duration", "10"]
