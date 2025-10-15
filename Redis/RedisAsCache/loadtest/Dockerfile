FROM python:3.11-slim

WORKDIR /load
RUN pip install --no-cache-dir locust==2.31.6 requests
COPY locustfile.py ./

EXPOSE 8089
CMD ["locust", "-f", "locustfile.py", "--host", "http://app:8000"]