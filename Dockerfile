# Use the official Python image from Docker Hub
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the .env file into the container
COPY .env /app/.env

# Copy the rest of the working directory contents into the container at /app
COPY . /app

# Expose port 5000 to the host
EXPOSE 5000

# Set the default command to run the app using Gunicorn with eventlet
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "4", "-b", "0.0.0.0:5000", "app:socketio"]
