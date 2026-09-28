#!/usr/bin/env python3
"""Provision the VANTOR Keycloak realm, idempotently, over the admin API.

Why this exists
---------------
VNT-036. `docker compose up` produced a Keycloak with no realm, no client and no
roles, so the documented quickstart could not issue a single token. The obvious
fix — hand Keycloak a JSON file via `--import-realm` — only gets you *most* of
the way, and the missing part is the one that matters:

* A realm file is static, so it cannot contain the service client's secret. The
  secret has to come from the environment, and `--import-realm` does not expand
  environment references.
* If the file names a literal placeholder as the secret, you have created a
  client whose secret is that literal string. That is strictly worse than having
  no client: it looks configured, and the first person to read the file learns
  the credential.
* If the file omits the secret, Keycloak generates a random one that nobody
  outside the container can read back, so the worker can never authenticate.
* `--import-realm` is also skipped when the realm already exists, so a restart
  after a secret rotation silently keeps the old credentials.

So the realm *shape* is imported from `realm-vantor.json`, and everything that
depends on a secret is reconciled here, through the admin API, on every start.
Running this twice is a no-op; running it after a rotation applies the rotation.

Usage (from inside the compose network):
    KEYCLOAK_URL=http://keycloak:8080 \
    KEYCLOAK_ADMIN=admin KEYCLOAK_ADMIN_PASSWORD=... \
    SERVICE_CLIENT_SECRET=... \
    python provision.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REALM = os.environ.get("KEYCLOAK_REALM", "vantor")
BASE = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080").rstrip("/")
ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN", "admin")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
SERVICE_CLIENT_ID = os.environ.get("SERVICE_CLIENT_ID", "vantor-service")
SERVICE_CLIENT_SECRET = os.environ.get("SERVICE_CLIENT_SECRET", "")
TEMPLATE = pathlib.Path(__file__).with_name("realm-vantor.json")

#: The only roles the worker's service account holds.
#:
#: VNT-024. This used to be `("Super Admin", "Procurement Admin",
#: "Procurement Manager")`, because the expiry roll required `Super Admin` and
#: the webhook drain required the operations roles. The result was a machine
#: account holding the platform's most powerful role, reachable by anything able
#: to read the secret out of the environment.
#:
#: `Service Identity` covers both of the worker's actual operations - the expiry
#: roll and the webhook drain - and nothing else. Least privilege for a scheduled
#: job is not a refinement; it is the difference between one leaked token and a
#: fully administrative one. Kept as data so the mapping is auditable rather than
#: implied by a string in a shell script.
SERVICE_ACCOUNT_ROLES = ("Service Identity",)


class Admin:
    """Minimal Keycloak admin-API client over urllib.

    Deliberately dependency-free: this image exists only to run this script, and
    adding a requests/httpx dependency would mean another thing to pin.
    """

    def __init__(self, base: str):
        self.base = base
        self.token: str | None = None

    def _request(self, method: str, path: str, body=None, *, raw_body=None):
        url = f"{self.base}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = "application/json"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
                return resp.status, (json.loads(payload) if payload else None)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                return exc.code, json.loads(payload)
            except (ValueError, TypeError):
                return exc.code, payload.decode("utf-8", "replace")

    def wait_ready(self, attempts: int = 60, delay: float = 5.0) -> None:
        """Block until the admin endpoint answers. Compose healthchecks are not
        a guarantee a dependent can rely on across restarts, so this waits too."""
        last = ""
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    f"{self.base}/realms/master", timeout=5
                ) as resp:
                    if resp.status == 200:
                        print("==> keycloak is up")
                        return
            except (urllib.error.URLError, OSError) as exc:
                last = str(exc)
            print(f"    waiting for keycloak ({attempt + 1}/{attempts}) {last}")
            time.sleep(delay)
        raise SystemExit("keycloak did not become ready")

    def login(self) -> None:
        form = urllib.parse.urlencode(
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": ADMIN_USER,
                "password": ADMIN_PASSWORD,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/realms/master/protocol/openid-connect/token",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.token = json.loads(resp.read())["access_token"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise SystemExit(
                f"admin login failed ({exc.code}): {detail}\n"
                f"Check KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD in .env."
            ) from exc

    # -- realm -------------------------------------------------------------
    def realm_exists(self) -> bool:
        status, _ = self._request("GET", f"/admin/realms/{REALM}")
        return status == 200

    def create_realm(self, template: dict) -> None:
        status, body = self._request("POST", "/admin/realms", template)
        if status not in (201, 204):
            raise SystemExit(f"realm creation failed ({status}): {body}")

    # -- roles -------------------------------------------------------------
    def ensure_roles(self, names) -> None:
        status, existing = self._request("GET", f"/admin/realms/{REALM}/roles")
        have = {r["name"] for r in existing} if status == 200 else set()
        for name in names:
            if name in have:
                continue
            payload = {"name": name, "description": f"Provisioned by deploy/keycloak/provision.py"}
            status, body = self._request(
                "POST", f"/admin/realms/{REALM}/roles", payload
            )
            if status not in (201, 204):
                raise SystemExit(f"could not create role {name!r} ({status}): {body}")
            print(f"    + role {name}")

    # -- clients -----------------------------------------------------------
    def find_client(self, client_id: str):
        status, body = self._request("GET", f"/admin/realms/{REALM}/clients")
        if status == 200 and isinstance(body, list):
            for c in body:
                if c.get("clientId") == client_id:
                    return c
        return None

    def ensure_service_client(self) -> str:
        """Ensure the worker's client exists with service accounts enabled, and
        that its secret is the configured one. Returns the client UUID."""
        found = self.find_client(SERVICE_CLIENT_ID)

        if found is None:
            payload = {
                "clientId": SERVICE_CLIENT_ID,
                "name": "VANTOR worker (machine identity)",
                "description": "Client-credentials identity for the RQ worker.",
                "enabled": True,
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "protocol": "openid-connect",
            }
            status, body = self._request("POST", f"/admin/realms/{REALM}/clients", payload)
            if status not in (201, 204):
                raise SystemExit(f"client creation failed ({status}): {body}")
            # 201 returns the representation including the id; re-read to be sure.
            found = self.find_client(SERVICE_CLIENT_ID)
            if not found:
                raise SystemExit("client created but could not be read back")
            print(f"    + client {SERVICE_CLIENT_ID}")
        else:
            if not found.get("serviceAccountsEnabled"):
                found["serviceAccountsEnabled"] = True
                found["publicClient"] = False
                self._request(
                    "PUT", f"/admin/realms/{REALM}/clients/{found['id']}", found
                )
                print(f"    * enabled service accounts on {SERVICE_CLIENT_ID}")

        # Always (re)assert the secret. This is what makes rotation work: the
        # value in .env is the truth, on every start.
        status, body = self._request(
            "PUT",
            f"/admin/realms/{REALM}/clients/{found['id']}/client-secret",
            {"type": "secret", "value": SERVICE_CLIENT_SECRET},
        )
        if status not in (204, 200):
            raise SystemExit(f"could not set the client secret ({status}): {body}")
        print(f"    * client secret for {SERVICE_CLIENT_ID} matches the environment")
        return found["id"]

    def ensure_service_account_roles(self) -> None:
        status, body = self._request(
            "GET", f"/admin/realms/{REALM}/clients/{SERVICE_CLIENT_ID}/service-account-user"
        )
        if status != 200 or not body:
            raise SystemExit(f"service account not found ({status}): {body}")
        user_id = body["id"]
        status, realm_roles = self._request("GET", f"/admin/realms/{REALM}/roles")
        wanted = {r["id"]: r for r in realm_roles if r["name"] in SERVICE_ACCOUNT_ROLES}
        if not wanted:
            raise SystemExit("no realm roles to grant; roles missing from the realm")
        self._request(
            "POST",
            f"/admin/realms/{REALM}/users/{user_id}/role-mappings/realm",
            list(wanted.values()),
        )
        print(f"    * service account holds {', '.join(SERVICE_ACCOUNT_ROLES)}")

    # -- users -------------------------------------------------------------
    def find_user(self, username: str):
        status, body = self._request("GET", f"/admin/realms/{REALM}/users")
        if status == 200 and isinstance(body, list):
            for u in body:
                if u.get("username") == username:
                    return u
        return None

    def ensure_bootstrap_user(self, spec: dict) -> str | None:
        username = spec["username"]
        existing = self.find_user(username)

        credentials = [
            {
                "type": "password",
                "value": c["value"],
                "temporary": c.get("temporary", False),
            }
            for c in spec.get("credentials", [])
        ]
        if existing is None:
            payload = {
                "username": username,
                "enabled": True,
                "emailVerified": True,
                "email": spec.get("email", ""),
                "firstName": spec.get("firstName", ""),
                "lastName": spec.get("lastName", ""),
                "attributes": spec.get("attributes", {}),
                "credentials": credentials,
            }
            status, body = self._request("POST", f"/admin/realms/{REALM}/users", payload)
            if status not in (201, 204):
                raise SystemExit(f"user creation failed ({status}): {body}")
            print(f"    + user {username}")
            existing = self.find_user(username)
            if not existing:
                raise SystemExit(f"user {username} created but could not be read back")
        else:
            # Update the mutable fields so a template change is applied to the
            # existing user rather than only to newly created ones.
            for field in ("email", "firstName", "lastName"):
                if field in spec:
                    existing[field] = spec[field]
            existing["attributes"] = spec.get("attributes", existing.get("attributes", {}))
            self._request("PUT", f"/admin/realms/{REALM}/users/{existing['id']}", existing)

        if credentials:
            # Passwords are write-only, so this is the only way to assert one.
            # It is also what makes an existing user's password track .env
            # instead of drifting from it after a rotation.
            self._request(
                "PUT",
                f"/admin/realms/{REALM}/users/{existing['id']}/reset-password",
                {"type": "password", "value": credentials[0]["value"], "temporary": False},
            )
            print(f"    * password for {username} tracks the configuration")
        return existing["id"]

    def grant_realm_roles(self, user_id: str, role_names) -> None:
        status, realm_roles = self._request("GET", f"/admin/realms/{REALM}/roles")
        if status != 200:
            raise SystemExit(f"could not list roles ({status})")
        wanted = [r for r in realm_roles if r["name"] in set(role_names)]
        self._request(
            "POST", f"/admin/realms/{REALM}/users/{user_id}/role-mappings/realm", wanted
        )
        print(f"    * {len(wanted)} realm roles granted")


def main() -> int:
    if not ADMIN_PASSWORD:
        print("error: KEYCLOAK_ADMIN_PASSWORD is not set", file=sys.stderr)
        return 2
    if not SERVICE_CLIENT_SECRET:
        print("error: SERVICE_CLIENT_SECRET is not set", file=sys.stderr)
        return 2

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    admin = Admin(BASE)
    admin.wait_ready()
    admin.login()

    if admin.realm_exists():
        print(f"==> realm {REALM} already exists; reconciling")
    else:
        print(f"==> creating realm {REALM}")
        # The service client's secret is set below, not in the payload: a realm
        # definition that carries a secret is a secret in a file in the repo.
        admin.create_realm(template)

    print("==> ensuring realm roles")
    admin.ensure_roles([r["name"] for r in template.get("roles", {}).get("realm", [])])

    print("==> ensuring the worker machine identity")
    admin.ensure_service_client()
    admin.ensure_service_account_roles()

    print("==> ensuring the bootstrap user")
    for user in template.get("users", []):
        user_id = admin.ensure_bootstrap_user(user)
        if user_id:
            admin.grant_realm_roles(user_id, user.get("realmRoles", []))

    print("==> provisioning complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
