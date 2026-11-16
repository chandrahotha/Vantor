# Provisions the Keycloak realm. Runs once, then exits.
#
# No apt install: the previous revision needed postgresql-client and reached
# into a sibling container's database to CREATE DATABASE. The separate
# keycloak-db service already has POSTGRES_DB=keycloak, so the postgres image
# creates it, and this image needs nothing but the interpreter. Fewer packages
# is fewer things to pin and fewer CVEs.
# Base image pinned by digest — a tag is a mutable name. Refresh with
# `python scripts/pin_digests.py`; `scripts/pin_digests.py --check` enforces it.
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

WORKDIR /app
COPY realm-vantor.json provision.py init.sh /app/
RUN chmod +x /app/init.sh

# Unprivileged: this container holds the admin password and the client secret.
RUN useradd --create-home --uid 10001 bootstrap \
 && chown -R bootstrap:bootstrap /app
USER bootstrap

ENTRYPOINT ["/app/init.sh"]
