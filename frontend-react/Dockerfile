# Stage 1: Development
FROM node:20-alpine AS development
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 2: Build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Padrão relativo (/api/v1): o nginx abaixo encaminha ao backend. Para um
# backend em outro domínio, passe a URL absoluta no build.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 3: Production
FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
# templates/ passa por envsubst no boot (imagem oficial do nginx)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV BACKEND_URL=http://api:8000 \
    NGINX_RESOLVER=127.0.0.11
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
