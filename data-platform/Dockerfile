# Airflow image with the extra client libraries our DAGs need.
# Everything else (postgres/amazon providers, httpx, pydantic) ships with the base image.
FROM apache/airflow:3.3.0-python3.12

RUN pip install --no-cache-dir "neo4j>=5.28"
