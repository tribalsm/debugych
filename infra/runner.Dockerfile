FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10002 --create-home runner
COPY services/runner services/runner
COPY demo/sample-python-app demo/sample-python-app
USER 10002:10002
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "services.runner.main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
