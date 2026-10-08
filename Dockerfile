# VANTOR — single container: web + API + SQLite.
#
# The repository's other Dockerfiles build the pieces of the Compose stack
# (Postgres, Redis, Keycloak, a worker). This image is the whole product in one
# process group with a file-backed database, which is what makes it deployable
# on a free tier: no managed database, no identity service, nothing to wire up.
#
# What you give up, stated plainly rather than discovered later:
#   * SQLite has no row-level security, so tenant isolation here is enforced by
#     the query layer alone, not by the database. Single-tenant use only.
#   * No Redis means no RQ worker and no beat scheduler. Nothing that depends on
#     background execution runs.
#   * Sign-in is local and passwordless: anyone who can reach the URL is the
#     operator. Do not put this on an untrusted network.
#
# For multi-tenant, background jobs or a real identity provider, use
# `docker compose up` instead — that stack is unchanged.

# ---- web -------------------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin: the browser talks to /api on whatever host serves the page, so
# the image needs no build-time knowledge of where it will be deployed. Baking
# `http://localhost:8000` in here is what makes an image work on the builder's
# machine and nowhere else.
ENV NEXT_PUBLIC_API_URL=""
# Next evaluates `rewrites()` at build time and writes the result into
# routes-manifest.json, so the proxy target has to be known here — setting it
# only at runtime leaves the manifest empty and every /api call falls through to
# the web app's own 404 handler. Inside this image the API is always on
# loopback, so the value is fixed and safe to bake.
ENV INTERNAL_API_URL="http://127.0.0.1:8000"
RUN npm run build

# ---- run -------------------------------------------------------------------
FROM python:3.13-slim AS run
WORKDIR /srv

# Node is needed at runtime because the web app is a Next server, not a bundle
# of static files: it renders the server components.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=web /web/.next/standalone ./web/
COPY --from=web /web/.next/static ./web/.next/static
# `output: "standalone"` does not copy `public/`. Miss this and every brand
# asset 404s — the sidebar renders an empty white plate where the logo should be.
COPY --from=web /web/public ./web/public

COPY deploy/single-container/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh \
 && mkdir -p /data \
 && useradd --system --uid 10001 vantor \
 && chown -R vantor:vantor /data /srv
USER vantor

ENV APP_ENV=production \
    DATABASE_URL=sqlite:////data/vantor.db \
    LOCAL_KEY_PATH=/data/session-signing-key.pem \
    UPLOAD_DIR=/data/uploads \
    STORAGE_DRIVER=filesystem \
    AUTH_MODE=local \
    PORT=8080 \
    API_PORT=8000 \
    NODE_ENV=production

# The database, the uploads and the session signing key all live here. Mount it
# or every restart is a fresh install and every open session is invalidated.
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"API_PORT\"]}/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["/usr/local/bin/start.sh"]
