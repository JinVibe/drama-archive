FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models TOKENIZERS_PARALLELISM=false

WORKDIR /app

# CPU-only torch keeps the image far smaller than the default CUDA wheels.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[embed]"

# The model (~2.2 GB) is downloaded on first start into the /models volume, not baked in.
RUN useradd --system --uid 10001 app && mkdir -p /models && chown app /models
USER app
EXPOSE 8090
CMD ["uvicorn", "ai_api.main:app", "--host", "0.0.0.0", "--port", "8090"]
