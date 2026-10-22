# Context prepared by run-integration-e2e.ps1 from npm ci's locked axe packages.
# Reuse the reviewed Linux browser runtime, without downloading another browser.
FROM debugych-integration-playwright:local
USER root
COPY axe-core /opt/runtime/node_modules/axe-core
COPY axe-playwright /opt/runtime/node_modules/@axe-core/playwright
COPY lucide-react /opt/runtime/node_modules/lucide-react
RUN mkdir -p /work/apps/web /work/outputs && chown 10000:10000 /work/outputs && ln -s /opt/runtime/node_modules /work/apps/web/node_modules
USER 10000:10000
WORKDIR /work/apps/web
ENTRYPOINT ["node", "/opt/runtime/node_modules/@playwright/test/cli.js"]
