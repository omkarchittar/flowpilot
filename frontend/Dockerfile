FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG FLOWPILOT_API_URL=http://api:8000
ENV FLOWPILOT_API_URL=$FLOWPILOT_API_URL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
USER node
EXPOSE 3001
CMD ["node", "server.js"]
