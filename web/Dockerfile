FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# The image's entrypoint fills ${API_UPSTREAM} from the environment at start (#14), so no API address is
# baked into the build.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
# A fallback so nginx still starts (and serves the app) where the env var is missing, e.g. a local docker run.
ENV API_UPSTREAM=http://localhost:8000
