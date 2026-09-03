FROM python:3.12-slim

# Install wait-for-it and uv
RUN apt-get update && apt-get install -y wait-for-it && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies without installing the project itself
RUN uv sync --frozen --no-install-project

# Copy source code
COPY . /app

# Ensure entrypoint is executable
RUN chmod +x /app/scripts/entrypoint.sh

# Run as non-root user
RUN useradd -m fceuser
RUN chown -R fceuser:fceuser /app
USER fceuser

# Set environment
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "scripts/worker_main.py"]
