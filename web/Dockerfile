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
# A fallback for a local `docker run`: the API on the host machine. Azure sets the API's internal address.
ENV API_UPSTREAM=http://host.docker.internal:8000
