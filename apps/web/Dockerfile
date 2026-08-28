# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /app
# Dependency layer on its own: only reinstalled when the manifests change.
COPY package.json package-lock.json* ./
RUN npm install

# --- dev --------------------------------------------------------------------
FROM node:22-alpine AS dev
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
# The source is bind-mounted over /app in compose, so node_modules has to be a
# named volume there or this layer is shadowed by the host's (empty) folder.
CMD ["npm", "run", "dev"]

# --- production -------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The API base is inlined into the client bundle at build time, so it must be
# supplied as a build arg for anything other than a localhost deploy.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 sajilo && adduser -u 10001 -G sajilo -D sajilo
COPY --from=build --chown=sajilo:sajilo /app/.next ./.next
COPY --from=build --chown=sajilo:sajilo /app/node_modules ./node_modules
COPY --from=build --chown=sajilo:sajilo /app/package.json ./package.json
COPY --from=build --chown=sajilo:sajilo /app/public ./public
USER sajilo
EXPOSE 3000
CMD ["npm", "run", "start"]
