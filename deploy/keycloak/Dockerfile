# Provisions the Keycloak realm. Runs once, then exits.
#
# No apt install: the previous revision needed postgresql-client and reached
# into a sibling container's database to CREATE DATABASE. The separate
# keycloak-db service already has POSTGRES_DB=keycloak, so the postgres image
# creates it, and this image needs nothing but the interpreter. Fewer packages
# is fewer things to pin and fewer CVEs.
FROM python:3.13-slim

WORKDIR /app
COPY realm-vantor.json provision.py init.sh /app/
RUN chmod +x /app/init.sh

# Unprivileged: this container holds the admin password and the client secret.
RUN useradd --create-home --uid 10001 bootstrap \
 && chown -R bootstrap:bootstrap /app
USER bootstrap

ENTRYPOINT ["/app/init.sh"]
