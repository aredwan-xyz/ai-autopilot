FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create directories
RUN mkdir -p reports credentials

# Non-root user for security
RUN useradd -m -u 1000 autopilot && chown -R autopilot:autopilot /app
USER autopilot

EXPOSE 8000

CMD ["python", "-m", "src.api.server"]
