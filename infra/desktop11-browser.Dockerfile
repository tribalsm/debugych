FROM debugych-integration-playwright:local
COPY --chown=10000:10000 pet /work/pet
RUN ln -s /opt/runtime/node_modules /work/pet/node_modules && mkdir -p /work/pet/evidence/v321 && chown -R 10000:10000 /work/pet
USER 10000:10000
WORKDIR /work/pet
ENTRYPOINT ["node","run-browser.mjs"]
