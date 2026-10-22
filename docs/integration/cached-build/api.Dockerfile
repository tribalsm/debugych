FROM debugych-uiux-api:local
COPY --chown=app:app apps apps
COPY --chown=app:app services services
COPY --chown=app:app demo demo
COPY --chown=app:app infra/migrations infra/migrations
COPY --chown=app:app alembic.ini .
