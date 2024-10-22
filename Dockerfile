# Use the official Python image from Docker Hub
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the .env file into the container
COPY .env /app/.env

# Copy the rest of the working directory contents into the container at /app
COPY . /app


# Set the default command to run the app using Gunicorn with eventlet
CMD ["python", "assistant.py", "start"]
