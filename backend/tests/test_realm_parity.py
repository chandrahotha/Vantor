"""The provisioned realm and the code that checks roles must agree.

Roles live in two places by necessity: Keycloak issues them and the API checks
them. Nothing in either system knows about the other, so a rename on one side
silently produces a permission nobody has — every request is refused, or worse,
every request is allowed, depending on which direction the drift went.

VNT-036. The realm is now provisioned automatically, which makes this drift
possible on every deploy instead of once at the start. So it is asserted here,
offline, with no Keycloak running.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
REPO = BACKEND.parent
REALM_FILE = REPO / "deploy" / "keycloak" / "realm-vantor.json"


def _referenced_roles() -> set[str]:
    r"""Every string literal the app uses as a role check.

    Collected via the AST rather than a regex because the role declarations are
    not all the same shape, and a regex silently misses most of them:

    * `WRITE_ROLES = {...}` and `APPROVER_ROLES: frozenset[str] = {...}`
      (Assign and AnnAssign are different node types);
    * `ACTION_ROLES = {"edit": {...}, ...}` and `TOOL_ROLES` are dicts *of* sets,
      so a `\{[^}]*\}` regex captures only the first inner set;
    * `require_roles("Approver", "Buyer")` passes roles positionally, with no
      assignment to match on at all;
    * `set(actor.roles) & {"Super Admin", "Auditor"}` inlines the set at the
      point of comparison.

    Any of those being missed would make this test agree with a realm that had
    lost roles, which is the exact failure it exists to catch.
    """
    found: set[str] = set()

    def literals(value) -> list[str]:
        """String literals that are *values*, not keys.

        `ACTION_ROLES` is `{"edit": {...}, "sign": {...}}`, so walking the dict
        naively yields the action names alongside the role names. The keys are
        the identifiers of the operations; only the sets are the roles.
        """
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return [value.value]
        if isinstance(value, ast.Dict):
            # Keys are action/tool names, not roles.
            return [s for v in value.values for s in literals(v)]
        if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return [s for v in value.elts for s in literals(v)]
        if isinstance(value, ast.Call):
            # e.g. frozenset({...}) — look through the argument.
            return [s for arg in value.args for s in literals(arg)]
        return [
            sub.value
            for sub in ast.walk(value)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
        ]

    def add(value) -> None:
        # No "looks like a role name" filter here. These sites are unambiguous
        # (a `*_ROLES` binding or a `require_roles` call), and a heuristic filter
        # is how `Buyer`, `Approver` and `Auditor` got dropped: they are single
        # words, so requiring a space in the name quietly excluded a third of
        # the roles while the test still looked like it was working.
        found.update(literals(value))

    def names(node) -> list[str]:
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            return [n for elt in node.elts for n in names(elt)]
        return []

    class Visitor(ast.NodeVisitor):
        def _handle_binding(self, target, value) -> None:
            if any(n.endswith("ROLES") for n in names(target)):
                add(value)

        def visit_Assign(self, node):
            for t in node.targets:
                self._handle_binding(t, node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):
            self._handle_binding(node.target, node.value)
            self.generic_visit(node)

        def visit_Call(self, node):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name and "require_roles" in name:
                for arg in node.args:
                    add(arg)
            self.generic_visit(node)

        def visit_BinOp(self, node):
            # `something & {"Role", "Role"}` — an inline role set at the point of
            # comparison. This context is weaker than the others, so it requires
            # at least one multi-word element: that keeps ordinary bitmask
            # arithmetic such as `flags & {"a", "b"}` from being read as a role
            # check, while every real role set contains e.g. "Super Admin".
            if isinstance(node.op, ast.BitAnd):
                for side in (node.left, node.right):
                    if isinstance(side, (ast.Set, ast.List, ast.Tuple)):
                        values = literals(side)
                        if any(" " in v for v in values):
                            found.update(values)
            self.generic_visit(node)

    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        Visitor().visit(tree)
    return found


@pytest.fixture(scope="module")
def realm() -> dict:
    assert REALM_FILE.exists(), f"the realm template is missing: {REALM_FILE}"
    return json.loads(REALM_FILE.read_text(encoding="utf-8"))


def test_realm_template_defines_every_role_the_api_checks(realm):
    declared = {r["name"] for r in realm["roles"]["realm"]}
    referenced = _referenced_roles()

    missing = sorted(referenced - declared)
    assert not missing, (
        "the API checks for roles the realm never issues; every holder of these "
        f"roles would be refused: {missing}"
    )


def test_realm_declares_no_unused_roles(realm):
    """Catches the other direction: a role in the realm that no code checks is
    either a typo or a permission that was granted and never enforced."""
    declared = {r["name"] for r in realm["roles"]["realm"]}
    unreferenced = sorted(declared - _referenced_roles() - {"Read Only"})
    assert not unreferenced, (
        f"realm roles no code checks for: {unreferenced}. Either a typo, or a "
        "permission granted in the identity provider and never enforced."
    )


def test_realm_contains_no_client_secret(realm):
    """The reason provision.py exists.

    A realm file is committed, so a secret in it is a published credential. The
    service client's secret is set from the environment by provision.py on every
    start, which is also what makes rotation work. This test is the thing that
    stops someone 'just adding it back' for convenience.
    """
    offenders = []
    for client in realm.get("clients", []):
        for field in ("secret", "clientAuthenticatorType"):
            if client.get(field):
                offenders.append(f"{client.get('clientId')}.{field}={client[field]!r}")
    for user in realm.get("users", []):
        for cred in user.get("credentials", []):
            # A password in the template is acceptable only for the single
            # documented bootstrap account, and only because it is local-only.
            if user.get("username") != "admin":
                offenders.append(f"user {user.get('username')} has a credential")
    assert not offenders, f"secrets must not live in the committed realm: {offenders}"


def test_service_client_cannot_use_a_browser_flow(realm):
    """The worker's identity is a machine identity.

    If it could do an authorization-code or implicit flow, a leaked secret would
    be enough to obtain a token with a human's consent screen, and the audit log
    would attribute worker actions to a user who never existed.
    """
    client = next(c for c in realm["clients"] if c["clientId"] == "vantor-service")
    assert client["serviceAccountsEnabled"] is True
    assert client["publicClient"] is False, "a machine identity must be confidential"
    assert client["standardFlowEnabled"] is False
    assert client["implicitFlowEnabled"] is False
    assert client["directAccessGrantsEnabled"] is False


def test_web_client_uses_pkce_and_is_public(realm):
    client = next(c for c in realm["clients"] if c["clientId"] == "vantor-web")
    assert client["publicClient"] is True
    assert client["serviceAccountsEnabled"] is False
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["redirectUris"], "a public client with no redirect URIs cannot log in"


def test_tenant_is_in_the_token(realm):
    """Every row in the database is tenant-scoped. If the token carries no
    tenant, a missing header silently means 'no tenant' rather than an error,
    and the query returns another tenant's rows or none at all."""
    mappers = next(c for c in realm["clients"] if c["clientId"] == "vantor-web")
    names = {m["config"]["claim.name"] for m in mappers.get("protocolMappers", [])}
    assert "tenant_id" in names, (
        f"tenant_id is not mapped into the token; claims are {names}"
    )


def test_registration_is_closed(realm):
    """Self-registration would let anyone create an account in a procurement
    system, and the role mapper would then be the only thing between them and an
    approval queue."""
    assert realm["registrationAllowed"] is False
    assert realm["resetPasswordAllowed"] is False
    assert realm["duplicateEmailsAllowed"] is False
    assert realm["bruteForceProtected"] is True
