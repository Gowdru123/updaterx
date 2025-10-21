# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    make \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment (recommended for Docker best practices)
RUN python -m venv /opt/venv

# Upgrade pip, setuptools, and wheel to ensure modern builds
RUN pip install --upgrade pip setuptools wheel

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Flask explicitly (can also go into requirements.txt)
RUN pip install flask

# Copy application code
COPY . .

# Ensure templates directory exists
RUN mkdir -p templates

# Expose port for web interface
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/api/status')" || exit 1

# Run the Flask application with the Telegram bot
CMD ["python", "app.py"]
