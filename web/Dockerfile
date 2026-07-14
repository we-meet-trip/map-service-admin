# syntax=docker/dockerfile:1

# ---- build stage ----------------------------------------------------------
# node:22-alpine has arm64 images, so this builds on a Raspberry Pi 4 too.
FROM node:22-alpine AS build
WORKDIR /app

# Install deps first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm ci

# Build the static SPA.
COPY . .
RUN npm run build

# ---- serve stage ----------------------------------------------------------
FROM nginx:alpine AS serve

# Replace the default site with our SPA + /api proxy config.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the compiled assets.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
