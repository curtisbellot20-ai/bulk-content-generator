FROM python:3.11-slim

# Install ffmpeg (required by moviepy for video processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create runtime directories
RUN mkdir -p uploads outputs

EXPOSE 8080

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
