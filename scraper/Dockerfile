# Use the same Python version as the backend for consistency
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies that might be needed by libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from the backend project as they are shared
COPY ./backend/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy both scraper and backend code into the image
# The services need code from both directories (e.g., for db connections)
COPY ./scraper /app/scraper
COPY ./backend /app/backend

# Set the python path so imports from 'app' (in backend) work correctly
ENV PYTHONPATH=/app

# Default command (can be overridden in docker-compose)
CMD ["echo", "Scraper service container running..."]