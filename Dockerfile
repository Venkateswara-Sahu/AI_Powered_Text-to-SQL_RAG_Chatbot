# Build stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for mysql-connector)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Flask port
EXPOSE 5000

# Environment
ENV FLASK_DEBUG=False
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "app.py"]
