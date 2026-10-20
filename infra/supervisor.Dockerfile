FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir docker==7.1.0 fastapi==0.115.12 uvicorn==0.34.2
COPY services/runner services/runner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# This trusted controller has Docker authority; untrusted job containers do not.
CMD ["uvicorn","services.runner.supervisor:app","--host","0.0.0.0","--port","8091"]
