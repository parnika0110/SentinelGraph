FROM node:22-slim AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# The browser calls the backend directly, so the public API URL is baked in
# at BUILD time. Passed as a build arg by the hosting provider.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["sh", "-c", "npm run start -- --port ${PORT:-3000} --hostname 0.0.0.0"]
