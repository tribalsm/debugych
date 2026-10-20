FROM node:22-bookworm-slim
WORKDIR /opt/runtime
COPY infra/playwright/package*.json ./
RUN npm ci && npx playwright install --with-deps chromium && useradd --uid 10000 sandbox
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
# Browser binaries must be readable by the non-root job user.
RUN mv /root/.cache/ms-playwright /opt/browsers && chmod -R a+rX /opt/browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY services/runner/playwright /opt/runtime/
USER 10000:10000
WORKDIR /tmp
ENTRYPOINT ["node", "/opt/runtime/harness.cjs"]
