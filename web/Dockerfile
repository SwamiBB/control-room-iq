FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
# Unprivileged nginx (Trivy DS-0002): runs as uid 101 and listens on 8080, not 80. Same template entrypoint.
FROM nginxinc/nginx-unprivileged:alpine
# OS package fixes the base image hasn't picked up yet (curl, brotli: Trivy).
USER root
# Upgrading can reinstall nginx's files as root; give its runtime directories back to the nginx user (uid 101).
RUN apk upgrade --no-cache  && chown -R 101:0 /var/cache/nginx /etc/nginx/conf.d  && chmod -R g+w /var/cache/nginx /etc/nginx/conf.d
USER 101
COPY --from=build /app/dist /usr/share/nginx/html
# The image's entrypoint fills ${API_UPSTREAM} from the environment at start (#14), so no API address is
# baked into the build.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
# A fallback for a local `docker run`: the API on the host machine. Azure sets the API's internal address.
ENV API_UPSTREAM=http://host.docker.internal:8000
