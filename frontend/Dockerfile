# Frontend image: Vite production build served by nginx with an SPA fallback.
# Built by CI with the `frontend/` directory as the build context; pushed to
# ghcr.io/sergeyanokhin/video-archive/frontend. `/api` routing is done by the
# Traefik Ingress on the cluster (locally by the Vite dev proxy), never by
# nginx — see docs/deployment.md.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
