#!/usr/bin/env python3
"""Resolve and record immutable digests for every image in the compose file.

VNT-035. The stack referenced `minio/minio:latest` and `ollama/ollama:latest`
behind environment indirection, so two people running the same commit could get
different images, and a rebuilt upstream tag silently changed what was tested.
A tag is a mutable name; a digest is the content.

Why a script and not a hand-copied list
---------------------------------------
A hand-copied digest list goes stale and nobody notices, because a stale digest
still pulls successfully -- it just pulls the old thing. So the digests live in
`.env` next to the image names, and `--check` (offline, no registry access) is
what CI runs: it fails when a digest is missing or is still a placeholder. The
network is only needed to *refresh*.

Usage:
    python scripts/pin_digests.py            # resolve and write digests to .env
    python scripts/pin_digests.py --check    # offline: verify .env is pinned
    python scripts/pin_digests.py --stdout   # print, change nothing

Registry authentication uses the standard anonymous-pull flow: a manifest GET,
then the token the 401's WWW-Authenticate challenge points at. That works for
Docker Hub and quay.io without credentials, and fails loudly rather than
silently falling back to a tag.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

#: `POSTGRES_IMAGE=...@${POSTGRES_DIGEST:-sha256:000...}` in compose expands to
#: an `image:` string, so the digests are pulled from the *default* in compose,
#: which is the thing a developer without a .env would run. If the defaults
#: change, the pin follows automatically.
COMPOSE = ROOT / "docker-compose.yml"

PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_RE = re.compile(
    r"^\s*image:\s*"
    r"\$\{(?P<var>[A-Z0-9_]+):-(?P<image>[^}]+)\}"
    r"@\$\{(?P<digestvar>[A-Z0-9_]+):-(?P<default>[^}]+)\}\s*$"
)

#: Manifest media types to ask for. Asking for the list gives us the multi-arch
#: index digest, which is what `image@sha256:` must point at: the per-architecture
#: manifest digest is not what the runtime resolves.
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def parse_compose_images(text: str) -> list[tuple[str, str, str, str]]:
    """Return (service-ish var, digest var, image reference, default digest)."""
    found = []
    for line in text.splitlines():
        m = IMAGE_RE.match(line)
        if m:
            found.append(
                (m.group("var"), m.group("digestvar"), m.group("image"), m.group("default"))
            )
    return found


def split_reference(ref: str) -> tuple[str, str]:
    """`quay.io/keycloak/keycloak:25.0` -> (registry, repository:tag).

    A bare name like `redis:7-alpine` is a Docker Hub official image, so the
    registry is docker.io and the repository is `library/redis`. Getting this
    wrong yields a 401 or a 404 that looks like the tag does not exist.
    """
    name, _, tag = ref.rpartition(":")
    if not name:  # no tag at all
        name, tag = ref, "latest"
    parts = name.split("/")
    if len(parts) == 1:
        return "registry-1.docker.io", f"library/{parts[0]}:{tag}"
    if "." not in parts[0] and ":" not in parts[0]:
        # e.g. `library/redis` or `user/repo` with no registry component.
        return "registry-1.docker.io", f"{'/'.join(parts)}:{tag}"
    return parts[0], f"{'/'.join(parts[1:])}:{tag}"


def _open(req: urllib.request.Request, timeout: float = 20.0):
    return urllib.request.urlopen(req, timeout=timeout)


def resolve_digest(ref: str) -> str:
    registry, repository = split_reference(ref)
    base = f"https://{registry}/v2/{repository}/manifests/{repository.rpartition(':')[2]}"
    req = urllib.request.Request(base, headers={"Accept": ACCEPT})
    try:
        with _open(req) as resp:
            return resp.headers["Docker-Content-Digest"]
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise SystemExit(f"{ref}: registry returned {exc.code} {exc.reason}")
        challenge = exc.headers.get("WWW-Authenticate", "")
        params = dict(
            re.findall(r'(\w+)="([^"]*)"', challenge)
        )
        realm = params.get("realm")
        if not realm:
            raise SystemExit(
                f"{ref}: registry demanded authentication with no usable challenge "
                f"({challenge!r}). Anonymous pull is not available for this image."
            )
        query = {}
        if params.get("service"):
            query["service"] = params["service"]
        if params.get("scope"):
            query["scope"] = params["scope"]
        token_req = urllib.request.Request(f"{realm}?{urllib.parse.urlencode(query)}")
        with _open(token_req) as tok:
            token = json.loads(tok.read())["token"]
        req = urllib.request.Request(
            base, headers={"Accept": ACCEPT, "Authorization": f"Bearer {token}"}
        )
        with _open(req) as resp:
            return resp.headers["Docker-Content-Digest"]


def read_env(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def check(images, env_lines) -> int:
    """Offline verification. No registry access: this is the CI gate.

    Two separate things are checked, because they fail for different reasons and
    only one of them can be checked in CI:

    * **Structural** — every `image:` line is of the form
      `${VAR:-name:tag}@${DIGEST_VAR:-...}` and no tag is `latest`. This needs
      nothing but the compose file, so it is the part CI can enforce on every
      push, and it is what catches someone reverting a service to a mutable tag.
    * **Values** — if a `.env` exists, the digests in it are real sha256 values
      rather than the zero placeholder. A developer's stale `.env` is caught
      here; CI has no `.env`, so this half is skipped there rather than faked.
    """
    present: dict[str, str] = {}
    for line in env_lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            present[k.strip()] = v.strip()

    problems: list[str] = []
    reported: set[str] = set()
    # Tuples are (image_var, digest_var, image_reference, default_digest).
    pinnable = {img for _var, _digest_var, img, _default in images}

    # Any `image:` line that is not in the pinnable form was reverted to a
    # mutable tag, and would be missed entirely: the regex only matches lines
    # that already use `${VAR:-image}@${DIGEST_VAR:-...}`, so the line that broke
    # the rule is the one line the checker cannot see. That is the exact failure
    # this gate exists to prevent, so every image line is accounted for.
    for raw in COMPOSE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped.startswith("image:"):
            continue
        value = stripped.split("image:", 1)[1].strip()
        match = IMAGE_RE.match(raw)
        if match and match.group("image") in pinnable:
            continue
        if match and match.group("image") not in pinnable:
            problems.append(f"{value}: duplicate image reference")
        else:
            problems.append(
                f"{value}: not digest-pinned. Use "
                "`image: ${NAME_IMAGE:-repo:tag}@${NAME_DIGEST:-sha256:<64 hex>}`")

    for _var, digest_var, image, default in images:
        if digest_var in reported:
            continue  # keycloak-db and postgres share one image and one digest
        reported.add(digest_var)

        if image.endswith(":latest") or ":latest" in image:
            problems.append(f"{image}: uses a mutable `latest` tag")
        if not DIGEST_RE.match(default) or default == PLACEHOLDER_DIGEST:
            pass  # a zero placeholder is the expected shipped default
        if not env_lines:
            continue  # no .env: structural check only

        value = present.get(digest_var)
        if not value:
            problems.append(f"{digest_var} is not set in .env (image {image})")
        elif value == PLACEHOLDER_DIGEST or not DIGEST_RE.match(value):
            problems.append(
                f"{digest_var} is a placeholder or malformed: {value!r}\n"
                f"    run: python scripts/pin_digests.py")
        elif value == default:
            problems.append(
                f"{digest_var} still matches the compose placeholder for {image}")

    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"all {len(images)} images are digest-pinned (structural check passed)")
    return 0


def write_env(images, digests, env_lines) -> None:
    updated: list[str] = []
    seen: set[str] = set()
    for line in env_lines:
        key = line.partition("=")[0].strip() if "=" in line else ""
        if key in digests:
            updated.append(f"{key}={digests[key]}")
            seen.add(key)
        else:
            updated.append(line)
    block = ["", "# --- Image digests (VNT-035) ---",
             "# Written by scripts/pin_digests.py. Refresh with the same command;",
             "# verify with --check. A tag is a mutable name, a digest is content."]
    for key, value in digests.items():
        if key not in seen:
            block.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(updated + block) + "\n", encoding="utf-8")
    print(f"wrote {len(digests)} digests to {ENV_FILE}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify only, no network")
    ap.add_argument("--stdout", action="store_true", help="print, change nothing")
    args = ap.parse_args()

    images = parse_compose_images(COMPOSE.read_text(encoding="utf-8"))
    if not images:
        print("error: no pinnable images found in docker-compose.yml", file=sys.stderr)
        return 2
    env_lines = read_env(ENV_FILE)

    if args.check:
        return check(images, env_lines)

    digests: dict[str, str] = {}
    failures = 0
    for _var, digest_var, image, _default in images:
        try:
            digest = resolve_digest(image)
        except SystemExit as exc:
            print(f"FAIL {image}: {exc}", file=sys.stderr)
            failures += 1
            continue
        if not DIGEST_RE.match(digest):
            print(f"FAIL {image}: registry returned an unusable digest {digest!r}",
                  file=sys.stderr)
            failures += 1
            continue
        digests[digest_var] = digest
        print(f"{image} -> {digest}")

    if failures:
        print(f"\n{failures} image(s) could not be pinned; nothing was written", file=sys.stderr)
        return 1
    if args.stdout:
        for k, v in digests.items():
            print(f"{k}={v}")
        return 0
    write_env(images, digests, env_lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
