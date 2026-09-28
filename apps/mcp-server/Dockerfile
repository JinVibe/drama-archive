FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

RUN useradd --system --uid 10001 app
USER app
EXPOSE 8100
CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8100"]
