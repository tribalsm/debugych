FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
COPY --chown=app:app apps apps
COPY --chown=app:app services services
COPY --chown=app:app demo demo
COPY --chown=app:app infra/migrations infra/migrations
COPY --chown=app:app alembic.ini .
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
