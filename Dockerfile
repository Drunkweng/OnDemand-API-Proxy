# Use official Python base image
FROM python:3.9-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port (will be overridden by PORT environment variable if set)
EXPOSE 7860

# Command to run the Flask app
CMD ["python", "2api.py"]
