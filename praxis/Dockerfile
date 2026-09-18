FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first (Docker layer caching — dependencies rarely change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port 8000 for the web application
EXPOSE 8000

# Start the FastAPI application with uvicorn
# --host 0.0.0.0 makes the app accessible from outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
