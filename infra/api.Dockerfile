FROM python:3.12-slim AS embeddings
COPY scripts/prepare-embeddings.py /prepare.py
RUN python /prepare.py --output /models
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-embeddings.txt && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
COPY --chown=app:app apps apps
COPY --chown=app:app services services
COPY --chown=app:app demo demo
COPY --chown=app:app infra/migrations infra/migrations
COPY --chown=app:app alembic.ini .
COPY --from=embeddings /models /opt/models/minilm
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RAG_MODEL_DIR=/opt/models/minilm
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
