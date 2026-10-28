FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web .
RUN npm run build
FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/dist /app/public
COPY scripts/serve-server-web.mjs /app/gateway.mjs
COPY infra/server/public-demo.json /app/demo.json
USER node
EXPOSE 8080
CMD ["node", "/app/gateway.mjs"]
