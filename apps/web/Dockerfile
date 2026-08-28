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
# The API base is inlined into the client bundle at build time — it is the URL
# the visitor's *browser* calls, so it cannot be supplied at runtime.
#
# Deliberately defaulted to localhost and then checked: a production image built
# without this arg would ship a bundle telling every user's browser to call
# their own machine. The page would render and nothing would load. Failing the
# build is far cheaper than finding that out from users.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ARG ALLOW_LOCALHOST_API=false
RUN if [ "$ALLOW_LOCALHOST_API" != "true" ] &&        echo "$NEXT_PUBLIC_API_BASE" | grep -qE 'localhost|127\.0\.0\.1'; then       echo "" >&2;       echo "ERROR: NEXT_PUBLIC_API_BASE is '$NEXT_PUBLIC_API_BASE'." >&2;       echo "It is baked into the client bundle, so every visitor's browser" >&2;       echo "would call their own machine and the app would not load." >&2;       echo "" >&2;       echo "  docker build --target production \\" >&2;       echo "    --build-arg NEXT_PUBLIC_API_BASE=https://api.your-domain/api/v1 ." >&2;       echo "" >&2;       echo "To build a localhost image on purpose, add" >&2;       echo "  --build-arg ALLOW_LOCALHOST_API=true" >&2;       exit 1;     fi     && npm run build

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
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3     CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["npm", "run", "start"]
