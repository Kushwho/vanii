# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set environment variables to ensure the Python output is not buffered (better for logging)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container first for better caching of dependencies
COPY requirements.txt .

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Upgrade langchain to the latest version if necessary
RUN pip install --no-cache-dir --upgrade langchain

# Copy the .env file into the container
COPY .env .

# Copy the rest of the application code into the container
COPY . .

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Command to start uWSGI server
CMD ["uwsgi", "--ini", "uwsgi.ini"]
