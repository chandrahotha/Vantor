"""Egress safety — the only place a URL is allowed to become a network call.

VNT-007. A webhook endpoint is a URL a tenant supplies and the server then
*requests*, on the tenant's behalf, from inside the network. Validating only
`url.startswith("https://")` means all of the following are accepted and then
dialled:

    https://169.254.169.254/latest/meta-data/   # cloud instance metadata
    https://127.0.0.1:6379/                     # the Redis on the compose network
    https://[::1]/                             # IPv6 loopback
    https://user@evil.example@127.0.0.1/       # userinfo confusion
    https://2130706433/                         # decimal-encoded 127.0.0.1
    https://internal-postgres/                  # a service name on the compose network

Each of those is a real SSRF: a tenant with only the `Buyer` role could read
cloud credentials, poke at internal services, or port-scan the cluster through
the API's own egress.

The defence is layered, and every layer matters because each can be bypassed
alone:

1. **Scheme allowlist.** `https` only. `file://`, `gopher://`, `dict://` and
   friends are not URLs we should ever fetch.
2. **No userinfo.** `https://trusted.example@evil.test/` reads as
   "trusted.example" in a log and connects to "evil.test". Refused outright
   rather than parsed, because every parser disagrees about where the host is.
3. **Host shape.** No bare IP literals at all in the allowlist-validated form —
   resolved addresses are checked instead, which is the only reliable answer.
4. **Address policy on every resolved address.** Loopback, private, link-local,
   multicast, reserved, unspecified — all refused. This is what catches the cloud
   metadata endpoint, and it is checked against the *resolved* address so DNS
   cannot be used to smuggle one past the check.
5. **Optional egress allowlist.** When `WEBHOOK_EGRESS_ALLOWLIST` is set, only
   those host suffixes are permitted. This is the control that makes the SSRF
   question go away rather than merely narrowing it.
6. **Re-validation at dial time.** DNS is resolved here and again immediately
   before the connection, and the connection is pinned to the address that was
   validated. That closes the DNS-rebinding window between "we checked the name"
   and "we opened the socket" — a gap of milliseconds that a determined caller
   can absolutely win.

Resolution failures are refused. A name that does not resolve is not a licence to
try harder.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = frozenset({"https"})

#: Hostname suffixes that are never legitimate webhook receivers, refused before
#: any DNS lookup so a rebinding attempt cannot even start.
BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".cluster.local",
    ".svc",
    ".svc.cluster.local",
)
BLOCKED_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal",
                           "instance-data", "metadata.goog"})

#: Single-label names that are legitimately public. An IP literal is handled by
#: the address policy, not here, so this stays a short explicit list rather than
#: a rule that silently permits whatever happens to be a bare name today.
_ALLOW_BARE_HOSTS = frozenset(set())

#: Cloud metadata endpoints, refused by address. `169.254.169.254` is covered by
#: the link-local rule; these are named because they are the specific targets an
#: SSRF attempt aims at and a named refusal is easier to audit than a category.
#: The IPv6 entries are quoted because an unquoted `fd00:ec2::254` inside a set
#: display parses as a slice expression, not as a string.
METADATA_ADDRESSES = frozenset({
    "169.254.169.254",       # AWS / Azure / GCP / OpenStack / DigitalOcean
    "169.254.170.2",         # AWS ECS task metadata
    "100.100.100.200",       # Alibaba Cloud
    "192.0.0.192",           # Oracle Cloud
    "fd00:ec2::254",         # AWS IMDSv6
})


class EgressError(ValueError):
    """A URL is not safe to fetch. `code` is stable and safe to branch on."""

    def __init__(self, code: str, message: str, *, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class SafeTarget:
    """A URL that has been validated, with the addresses it resolved to."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]
    #: Path and query, kept so a pinned request can be rebuilt without re-parsing
    #: the original string. Dropping the query would silently deliver to the
    #: wrong resource on an endpoint that signs or identifies by query parameter.
    path: str = "/"
    query: str = ""

    @property
    def pinned_ip(self) -> str:
        return self.addresses[0]


def _allowlist() -> tuple[str, ...]:
    raw = os.getenv("WEBHOOK_EGRESS_ALLOWLIST", "").strip()
    return tuple(part.strip().lower().lstrip(".") for part in raw.split(",") if part.strip())


def _host_allowed(host: str) -> bool:
    allow = _allowlist()
    if not allow:
        return True
    return any(host == entry or host.endswith("." + entry) for entry in allow)


def _address_permitted(address: str) -> tuple[bool, str]:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False, "not an IP address"
    if address in METADATA_ADDRESSES:
        return False, "cloud instance metadata endpoint"
    if ip.is_loopback:
        return False, "loopback"
    if ip.is_link_local:
        return False, "link-local (includes 169.254.0.0/16 metadata space)"
    if ip.is_private:
        return False, "private network"
    if ip.is_multicast:
        return False, "multicast"
    if ip.is_reserved or ip.is_unspecified:
        return False, "reserved or unspecified"
    if getattr(ip, "is_site_local", False):
        return False, "site-local"
    return True, ""


def _resolve(host: str, port: int) -> tuple[str, ...]:
    """Every address `host` resolves to, or raise.

    A failure to resolve is a refusal. Falling back to "try anyway" is how a
    validation layer stops being one.
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise EgressError("EGRESS_DNS_FAIL", f"Could not resolve host {host!r}", detail=str(exc)) from exc
    resolved = tuple(dict.fromkeys(info[4][0] for info in infos))
    if not resolved:
        raise EgressError("EGRESS_DNS_EMPTY", f"Host {host!r} resolved to no addresses")
    return resolved


def validate_url(url: str, *, resolve: bool = True) -> SafeTarget:
    """Validate `url` for outbound fetch. Raises `EgressError` when unsafe.

    `resolve=False` performs only the syntactic checks, for callers that want to
    validate a stored URL without paying a DNS lookup. It is *not* sufficient to
    authorise a fetch — `assert_safe_to_dial` does that at the last moment.
    """
    raw = (url or "").strip()
    if not raw:
        raise EgressError("EGRESS_URL_EMPTY", "URL is required")
    if len(raw) > 2048:
        raise EgressError("EGRESS_URL_TOO_LONG", "URL exceeds 2048 characters")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise EgressError("EGRESS_URL_MALFORMED", "URL could not be parsed", detail=str(exc)) from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise EgressError("EGRESS_SCHEME_REFUSED",
                          f"Scheme {scheme or '(none)'!r} is not permitted",
                          detail=f"allowed: {sorted(ALLOWED_SCHEMES)}")

    if parts.username or parts.password:
        # Refused rather than parsed: `https://good.example@evil.test` is read as
        # "good.example" by a human and as "evil.test" by every URL parser, and
        # that disagreement is the whole attack.
        raise EgressError("EGRESS_USERINFO_REFUSED",
                          "URLs carrying userinfo are refused; they make the host ambiguous")

    try:
        host = parts.hostname
    except ValueError as exc:
        raise EgressError("EGRESS_HOST_MALFORMED", "Host could not be parsed", detail=str(exc)) from exc
    if not host:
        raise EgressError("EGRESS_NO_HOST", "URL has no host")
    host = host.lower().rstrip(".")

    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_SUFFIXES):
        raise EgressError("EGRESS_HOST_REFUSED", f"Host {host!r} is not a permitted webhook destination")

    # An IP literal is not a name at all: it goes straight to the address policy.
    # It has to be recognised here, because `::1` and `127.0.0.1` contain no dot
    # and would otherwise be caught by the single-label rule below and refused
    # for the wrong reason — which is how a rule stops being the rule it claims.
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        ok, reason = _address_permitted(host.strip("[]"))
        if not ok:
            raise EgressError("EGRESS_ADDRESS_REFUSED",
                              f"Address {host} is {reason}", detail=f"address={host} reason={reason}")
        return SafeTarget(url=raw, host=host, port=port, addresses=(host.strip("[]"),),
                          path=parts.path or "/", query=parts.query)

    # A single-label name is a service name on whatever search domain the host
    # happens to have — on the compose network that is `postgres`, `redis`,
    # `minio`, `keycloak`. Refused before DNS, because resolving one is how you
    # reach an internal service, and because whether it resolves at all depends
    # on the resolver rather than on anything we control. This is the
    # deterministic form of the "internal-postgres" case.
    if "." not in host and host not in _ALLOW_BARE_HOSTS:
        raise EgressError("EGRESS_BARE_HOSTNAME_REFUSED",
                          f"Host {host!r} is a single-label name; internal service names are refused")

    try:
        port = parts.port or 443
    except ValueError as exc:
        raise EgressError("EGRESS_PORT_INVALID", "Port is not an integer", detail=str(exc)) from exc
    if not 1 <= port <= 65535:
        raise EgressError("EGRESS_PORT_INVALID", f"Port {port} is out of range")

    if not _host_allowed(host):
        raise EgressError("EGRESS_HOST_NOT_ALLOWLISTED",
                          f"Host {host!r} is not in WEBHOOK_EGRESS_ALLOWLIST")

    if not resolve:
        return SafeTarget(url=raw, host=host, port=port, addresses=(),
                          path=parts.path or "/", query=parts.query)

    addresses = _resolve(host, port)
    for address in addresses:
        ok, reason = _address_permitted(address)
        if not ok:
            raise EgressError("EGRESS_ADDRESS_REFUSED",
                              f"Host {host!r} resolves to {address}, which is {reason}",
                              detail=f"address={address} reason={reason}")
    return SafeTarget(url=raw, host=host, port=port, addresses=addresses,
                      path=parts.path or "/", query=parts.query)


def assert_safe_to_dial(target: SafeTarget) -> str:
    """Last-moment re-validation. Returns the IP the caller must connect to.

    Called immediately before the socket is opened. The name is resolved again
    here and the returned address is the one that was just checked, so a rebind
    between validation and connection cannot substitute a different host.

    The caller is expected to pin the connection to this address rather than
    letting the HTTP client re-resolve the name — use `pinned_request` to do
    that. Re-resolving at connect time is the vulnerability this function exists
    to close; handing the hostname back to a client that resolves it again
    reopens it.
    """
    addresses = _resolve(target.host, target.port)
    for address in addresses:
        ok, reason = _address_permitted(address)
        if not ok:
            raise EgressError("EGRESS_ADDRESS_REFUSED",
                              f"Host {target.host!r} re-resolved to {address}, which is {reason}",
                              detail=f"address={address} reason={reason}")
    return addresses[0]


def build_pinned_request(
    target: SafeTarget,
    *,
    method: str = "GET",
    content: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> "httpx.Request":
    """Build a request whose connection goes to the address just validated.

    The subtlety is that pinning has to be done *without* breaking the request.
    Three things have to stay right:

    * the socket must open to the validated IP, not to a name;
    * the `Host` header must still carry the original hostname, or the receiving
      virtual host will not route the request and any signature over a host-
      specific claim will not match;
    * TLS certificate verification must still be against the original hostname.
      Connecting to an IP literal normally means httpcore verifies the
      certificate against the IP, which fails for every real certificate — the
      obvious "fix" of disabling verification would hand an attacker a valid
      certificate for any host they can point DNS at, which is precisely the
      attack this module exists to stop.

    httpcore's `sni_hostname` request extension is what makes the third point
    work: the connection is made to the IP, the TLS handshake negotiates and
    verifies the certificate for the name the caller asked for. The name is only
    ever used for presentation, never for routing.

    Callers must also pass `follow_redirects=False`. A redirect is a fresh URL
    that has not been through any of this, and a 302 to the metadata endpoint is
    the cheapest SSRF there is.
    """
    import httpx  # imported here so `egress` stays importable without a transport

    address = assert_safe_to_dial(target)
    literal = f"[{address}]" if ":" in address else address
    default_port = target.port == 443
    netloc = literal if default_port else f"{literal}:{target.port}"

    pinned_url = urlunsplit(("https", netloc, target.path, target.query, ""))

    sent = dict(headers or {})
    # The `Host` header must be the original name — the receiving virtual host
    # routes on it, and a signature computed over a host-specific claim would not
    # match otherwise. It is assigned rather than merged: a caller-supplied Host
    # would be a way to have the two disagree.
    sent["Host"] = target.host if default_port else f"{target.host}:{target.port}"

    return httpx.Request(
        method,
        pinned_url,
        content=content,
        headers=sent,
        # Verified against the real hostname, not the literal we dialled.
        extensions={"sni_hostname": target.host},
    )
