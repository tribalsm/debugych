FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.5 coverage==7.8.0 fastapi==0.115.12 httpx==0.28.1 && useradd --uid 10000 sandbox
COPY services/runner/harness.py /opt/harness.py
COPY services/runner/pytest_bootstrap.py /opt/pytest_bootstrap.py
COPY infra/sandbox-pytest.ini /opt/pytest.ini
USER 10000:10000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/python", "-I", "/opt/harness.py"]
