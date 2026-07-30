# Multi-stage build: compile the Vite SPA, then serve the static bundle with nginx.
#
# IMPORTANT: Vite inlines import.meta.env.VITE_* at BUILD time, so VITE_API_URL
# must be passed as a build-arg pointing at the PUBLIC backend URL. Example:
#   docker build --build-arg VITE_API_URL=https://scitrek.example.org -t uvs-frontend ./frontend
# (docker-compose.prod.yml wires this from the VITE_API_URL env var.)
#
# Node 20 is required — the repo's Vite 7 toolchain does not support Node 18.

# ---- build stage ----
FROM node:20-alpine AS build
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
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
