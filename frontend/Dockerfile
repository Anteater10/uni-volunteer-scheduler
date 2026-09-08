# Multi-stage build: compile the Vite SPA, then serve the static bundle with nginx.
#
# IMPORTANT: Vite inlines import.meta.env.VITE_* at BUILD time, so VITE_API_URL
# must be passed as a build-arg pointing at the PUBLIC backend URL. Example:
#   docker build --build-arg VITE_API_URL=https://scitrek.example.org -t uvs-frontend ./frontend
# (docker-compose.prod.yml wires this from the VITE_API_URL env var.)
#
# Node 20 is required — the repo's Vite 7 toolchain does not support Node 18.

# ---- build stage ----
FROM node:26-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# Copilot surfaces (FAB, admin nav, feedback page) are hidden unless this is
# baked in as "true" — mirrors the backend's COPILOT_ENABLED feature flag.
ARG VITE_COPILOT_ENABLED=false
ENV VITE_COPILOT_ENABLED=$VITE_COPILOT_ENABLED
RUN npm run build

# ---- serve stage ----
# nginx-unprivileged, not plain nginx: the stock image starts its master
# process as root (F4). This variant runs entirely as uid 101 and therefore
# cannot bind a privileged port, which is why nginx.conf listens on 8080 and
# Caddy proxies to frontend:8080. Nothing publishes this port to the host —
# Caddy is the only consumer — so the change is internal to the compose
# network.
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# Already the image's default; stated so a future base-image swap that drops
# it fails review rather than silently restoring root.
USER 101
EXPOSE 8080
