FROM node:22-alpine AS build
WORKDIR /web
# Lockfile is authoritative: no `|| npm install` fallback, or CI and prod diverge silently.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /web
ENV NODE_ENV=production
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
