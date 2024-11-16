FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Set the working directory to appuser's home
WORKDIR /home/appuser

CMD ["python", "."]