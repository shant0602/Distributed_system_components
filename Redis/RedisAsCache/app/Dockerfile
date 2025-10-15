FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py cache.py provider_openmeteo.py ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# Use multiple workers for production-ish behavior
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
