
# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install system build dependencies required for aiohttp and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libffi-dev \
    libssl-dev \
    make \
    git \
    pkg-config \
    cmake \
    cargo \
    rustc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install build tools, then install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel Cython && \
    pip install --no-cache-dir --verbose -r requirements.txt

# Copy application files
COPY . .

# Expose port 5000
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
