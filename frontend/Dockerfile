# Base images are pinned by digest — a tag is a mutable name, so the image built
# today and the image built next week would not be the same thing.
# `scripts/pin_digests.py --check` enforces this on every push.
FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /web
# Lockfile is authoritative: no `|| npm install` fallback, or CI and prod diverge silently.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# `NEXT_PUBLIC_API_URL` is inlined into the browser bundle when `next build`
# runs, so it has to arrive as a build arg: a runtime env var cannot rewrite a
# bundle that is already written. The default keeps the historical behaviour for
# a plain `docker build` with no args.
#
# Pass "" for same-origin — the shape docker-compose.yml uses. Any address
# baked at build time is an address the browser must be able to reach, and
# `http://localhost:8000` is only reachable on the machine that built the image;
# that made every API call fail from everywhere else on an otherwise-healthy
# stack.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
# Next evaluates `rewrites()` at build time and writes the result into
# routes-manifest.json, so the proxy target must be known here too — setting it
# only at runtime leaves every /api call to fall through to the app's own 404.
ARG INTERNAL_API_URL=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
RUN npm run build

FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS run
WORKDIR /web
ENV NODE_ENV=production
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
