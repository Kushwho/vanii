# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies and build tools (including gcc)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libssl-dev make build-essential portaudio19-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt


# Copy the .env file into the container
COPY .env /app/.env

# Copy the rest of the working directory contents into the container at /app
COPY . /app

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Run app_socket.py with uWSGI using eventlet when the container launches
CMD ["uwsgi", "--ini", "uwsgi.ini"]
