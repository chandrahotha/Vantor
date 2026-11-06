#!/usr/bin/env python3
"""Resolve and record immutable digests for every image the project runs.

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
network is only needed to *refresh*, and to ask `--verify-remote` whether a pin
has drifted from the tag it pins.

The compose file pins each image twice over: `${NAME_DIGEST:-sha256:…}` carries
the real pin as the default, and `.env` can override it deliberately. `--check`
validates the default whether or not a `.env` exists, because the default is what
a clone with no `.env` runs and CI has no `.env` at all.

Two places name an image, and both are checked
----------------------------------------------
* **`docker-compose.yml`** — the images a developer runs. These are pinned
  through `.env` indirection, because the compose file is meant to be
  editable by a developer who has their own `.env`.
* **`.github/workflows/ci.yml`** — the images the CI jobs run. These are pinned
  inline in the workflow, because a CI job has no `.env` and the workflow is
  what names the image. The reason for pinning is identical, so the same
  `--check` gate polices both.

The compose file's `image:` lines are a different shape from the workflow's:
compose interpolates `${VAR:-image}@${DIGEST_VAR:-...}`, and a workflow names
a literal `image: repo:tag@sha256:...`. Two parsers, one gate.

Usage:
    python scripts/pin_digests.py            # resolve and write digests to .env
    python scripts/pin_digests.py --check    # offline: verify every pin is real
    python scripts/pin_digests.py --stdout   # print, change nothing
    python scripts/pin_digests.py --verify-remote  # network: has any pin drifted?

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

#: The CI workflow. Its service images are pinned inline rather than through
#: `.env` indirection: a CI job has no `.env`, and the workflow is the file
#: that names the image, so that is where the pin belongs.
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: Every Dockerfile that ships. The `docker` Dependabot ecosystem does not
#: recurse, so these are listed explicitly — the same reason the compose file
#: needs one entry per service.
DOCKERFILES = [
    ROOT / "Dockerfile",
    ROOT / "backend" / "Dockerfile",
    ROOT / "worker" / "Dockerfile",
    ROOT / "frontend" / "Dockerfile",
    ROOT / "deploy" / "keycloak" / "Dockerfile",
]

PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_RE = re.compile(
    r"^\s*image:\s*"
    r"\$\{(?P<var>[A-Z0-9_]+):-(?P<image>[^}]+)\}"
    r"@\$\{(?P<digestvar>[A-Z0-9_]+):-(?P<default>[^}]+)\}\s*$"
)

#: A workflow's `image:` key with a literal scalar value — a GitHub Actions
#: `services:` entry or a `container:` block. Deliberately a plain scalar:
#: compose's `image:` lines interpolate `${VAR:-...}` and are handled by
#: `IMAGE_RE` instead.
CI_IMAGE_RE = re.compile(r"^\s*image:\s*(?P<ref>[^\s#]+)\s*(?:#.*)?$")

#: A Dockerfile `FROM` line. The reference is the part before a stage alias
#: (`AS name`) and may carry a digest. The alias, when present, defines a
#: build stage rather than naming a base image.
DOCKER_FROM_RE = re.compile(
    r"^\s*FROM\s+(?P<ref>[^\s]+)"
    r"(?:\s+AS\s+(?P<alias>[^\s]+))?\s*$",
    re.IGNORECASE,
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


def parse_ci_images(text: str) -> list[tuple[int, str]]:
    """Return `(line number, image reference)` for every `image:` line.

    The line number is carried because a workflow is long and a bare image
    name does not say where it is; the failure message has to point at the
    exact line to be actionable.
    """
    found: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        m = CI_IMAGE_RE.match(raw)
        if m:
            found.append((number, m.group("ref")))
    return found


def check_ci_images(text: str) -> list[str]:
    """Every container image a CI job runs must be pinned to a digest.

    The rule is deliberately strict: an `image:` line in the workflow must
    carry a literal `@sha256:<64 hex>`. A dynamically interpolated image
    (`${{ ... }}`) is therefore rejected rather than skipped, because a gate
    that quietly exempts a line is a gate with a hole in it — and exempting
    one here would mean the *one* image that changes without a commit is the
    one the gate does not see. If a dynamic image is ever genuinely needed,
    that is a deliberate change to this check, not something to slip through.
    """
    problems: list[str] = []
    for number, ref in parse_ci_images(text):
        if "@" not in ref:
            problems.append(
                f"{CI_WORKFLOW.name} line {number}: {ref} is not digest-pinned. "
                "Use `image: repo:tag@sha256:<64 hex>`"
            )
            continue
        _name, _, digest = ref.rpartition("@")
        if not DIGEST_RE.match(digest):
            problems.append(
                f"{CI_WORKFLOW.name} line {number}: {ref} has a malformed digest "
                f"{digest!r} — expected sha256:<64 hex>"
            )
        if ":latest" in ref:
            problems.append(
                f"{CI_WORKFLOW.name} line {number}: {ref} uses a mutable `latest` tag"
            )
    return problems


def parse_dockerfile_bases(text: str) -> list[tuple[int, str]]:
    """Return `(line number, base reference)` for every `FROM` line.

    A `FROM` that names a build stage (`FROM web AS run`, where `web` was
    defined earlier in this same file) refers to a stage this Dockerfile
    already built — not to an image to pull — so it is not a base image.
    Stage names are tracked as they are defined rather than guessed from the
    reference's shape: a stage alias is a bare word, but `python:3.14-slim` is
    also a bare word before the colon, and only the file itself says which one
    it is.

    A `FROM` that *defines* a stage (`FROM node:22-alpine AS web`) is still a
    base image — the stage is just also named — so it is counted and its
    digest is required.
    """
    found: list[tuple[int, str]] = []
    stages: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = DOCKER_FROM_RE.match(raw)
        if not m:
            continue
        ref = m.group("ref")
        alias = m.group("alias")
        if ref.lower() in stages:
            # A previous stage, not a registry image. It cannot carry a
            # digest, and it does not need one.
            continue
        found.append((number, ref))
        if alias:
            stages.add(alias.lower())
    return found


def check_dockerfile_bases(path: pathlib.Path) -> list[str]:
    """Every base image a Dockerfile builds from must be pinned to a digest.

    The base image is where the build's supply chain enters: it carries the
    system packages, the interpreter, and the `npm ci` / `pip install` that
    run on top of it. A mutable tag there means the image produced by the same
    commit can differ from one day to the next — and the build was never run
    by CI, so nothing would have noticed.
    """
    problems: list[str] = []
    for number, ref in parse_dockerfile_bases(path.read_text(encoding="utf-8")):
        if "@" not in ref:
            problems.append(
                f"{path.relative_to(ROOT)} line {number}: {ref} is not digest-pinned. "
                "Use `FROM repo:tag@sha256:<64 hex>`"
            )
            continue
        _name, _, digest = ref.rpartition("@")
        if not DIGEST_RE.match(digest):
            problems.append(
                f"{path.relative_to(ROOT)} line {number}: {ref} has a malformed digest "
                f"{digest!r} — expected sha256:<64 hex>"
            )
        if ":latest" in ref:
            problems.append(
                f"{path.relative_to(ROOT)} line {number}: {ref} uses a mutable `latest` tag"
            )
    return problems


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


def manifest_url(ref: str) -> str:
    """The registry v2 manifest URL for an image reference.

    Split out from `resolve_digest` so the URL shape can be checked without a
    network call — `repository` is `name:tag` (e.g. `library/redis:7-alpine`),
    and the registry API takes the name and the reference as separate path
    segments. Passing `name:tag` as the name segment doubles the tag into the
    URL (`/v2/library/redis:7-alpine/manifests/7-alpine`), which 404s on
    Docker Hub and fails token auth on quay.io because the same string leaks
    into the scope it requests (`repository:name%3Atag:pull`). That shape
    looked plausible enough to ship with zero coverage until it was run
    against a real registry.
    """
    registry, repository = split_reference(ref)
    name, _, tag = repository.rpartition(":")
    return f"https://{registry}/v2/{name}/manifests/{tag}"


def resolve_digest(ref: str) -> str:
    base = manifest_url(ref)
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
        # The token exchange and the authenticated manifest GET are both ordinary
        # network calls that can fail for reasons that have nothing to do with the
        # image — a proxy returning 400, a captive portal, a transient 5xx. Left
        # unhandled, that `urllib.error.HTTPError` propagated out of this function
        # and aborted the entire run, so one unreachable registry discarded the
        # digests for every other image that had resolved fine. Each image is
        # pinned independently in `main`, and an exception that escapes here broke
        # that isolation. A network error is a per-image failure, not a crash.
        try:
            with _open(token_req) as tok:
                token = json.loads(tok.read())["token"]
            req = urllib.request.Request(
                base, headers={"Accept": ACCEPT, "Authorization": f"Bearer {token}"}
            )
            with _open(req) as resp:
                return resp.headers["Docker-Content-Digest"]
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read()[:200].decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - the body is diagnostic only
                pass
            raise SystemExit(
                f"{ref}: authenticated manifest request returned {exc.code} "
                f"{exc.reason}{f' ({body})' if body else ''}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SystemExit(f"{ref}: could not reach {urllib.parse.urlparse(base).netloc} ({exc})") from exc


def read_env(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def check_compose_default(image: str, default: str) -> list[str]:
    """The digest written into the compose default must be a real one.

    The default in `${NAME_DIGEST:-sha256:…}` is what a clone with no `.env`
    actually runs. It used to be the zero placeholder for every service, so the
    documented install path resolved images that do not exist and failed at pull
    time — while `docker compose config`, which interpolates without ever
    contacting a registry, reported the file as valid. The default is checked
    independently of `.env`, because a clone has no `.env` at all and the
    default is what such a clone runs.
    """
    if default == PLACEHOLDER_DIGEST:
        return [
            (
                f"{image}: the compose default digest is the zero placeholder, so a "
                "clone with no `.env` resolves an image that cannot be pulled\n"
                "    run: python scripts/pin_digests.py and write the result into the "
                "`@${NAME_DIGEST:-sha256:…}` default in docker-compose.yml"
            )]
    if not DIGEST_RE.match(default):
        return [f"{image}: the compose default digest {default!r} is not sha256:<64 hex>"]
    return []


def check(images, env_lines) -> int:
    """Offline verification. No registry access: this is the CI gate.

    Several separate things are checked, because they fail for different reasons
    and only some of them can be checked in CI:

    * **Shape (compose)** — every `image:` line is of the form
      `${VAR:-name:tag}@${DIGEST_VAR:-...}` and no tag is `latest`. This catches
      someone reverting a service to a mutable tag.
    * **The compose pin** — the digest in that default is a real sha256 value. A
      clone with no `.env` runs exactly that string, so a zero placeholder there
      was a broken default install. It is checked whether or not a `.env` exists;
      the placeholder stayed green for two reasons at once — this half skipped
      itself when `.env` was absent, and CI deleted the `.env` it had just copied
      before running this command.
    * **`.env` values** — if a `.env` exists, any digest set in it is real. Blank
      means "use the pin in docker-compose.yml", which is the supported default.
    * **One image, one digest** — an image named in both compose and the workflow
      must carry the same pin, or CI certifies an image the stack does not run.
    * **Shape (CI workflow)** — every image a CI job runs carries a
      literal digest. The CI images are pinned in the workflow rather than in
      `.env`, and the reason is the same as for compose, so they are gated by
      the same command.
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
        problems.extend(check_compose_default(image, default))

        if not env_lines:
            continue  # nothing to say about a .env that does not exist

        value = present.get(digest_var)
        if not value:
            continue  # blank means "use the pin in docker-compose.yml"
        if value == PLACEHOLDER_DIGEST or not DIGEST_RE.match(value):
            problems.append(
                f"{digest_var} is a placeholder or malformed: {value!r}\n"
                f"    run: python scripts/pin_digests.py")

    # The CI workflow names its own images, inline. They are not in `.env`,
    # so the compose half of this gate cannot see them.
    ci_images: list[tuple[int, str]] = []
    if CI_WORKFLOW.exists():
        ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
        ci_images = parse_ci_images(ci_text)
        problems.extend(check_ci_images(ci_text))
        problems.extend(check_pin_consistency(images, ci_images))
    else:
        problems.append(f"{CI_WORKFLOW.name} is missing — the CI images cannot be checked")

    # The Dockerfiles build from base images. Those are the supply chain the
    # build actually sits on, and nothing else in this gate can see them.
    dockerfile_bases = 0
    for dockerfile in DOCKERFILES:
        if not dockerfile.exists():
            problems.append(f"{dockerfile.relative_to(ROOT)} is missing — its base images cannot be checked")
            continue
        dockerfile_bases += len(parse_dockerfile_bases(dockerfile.read_text(encoding="utf-8")))
        problems.extend(check_dockerfile_bases(dockerfile))

    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1
    print(
        f"all {len(images)} compose images, {len(ci_images)} CI service images and "
        f"{dockerfile_bases} Dockerfile base images are digest-pinned, and the "
        "compose defaults carry real digests"
    )
    return 0


def check_pin_consistency(
    compose_images: list[tuple[str, str, str, str]],
    ci_images: list[tuple[int, str]],
) -> list[str]:
    """An image named in both compose and the workflow must carry one digest.

    `redis:7-alpine` was pinned to two different digests in these two files, and
    every existing rule passed: each file was asked whether it had *a* digest,
    never whether the two agreed. CI therefore certified an image the shipped
    stack does not run, which is the one thing a supply-chain pin exists to
    prevent. References are matched on the `repo:tag` string as written, so an
    image spelled with an explicit `docker.io/` prefix in one file would not be
    recognised as the same image — that is a known limit of this check, not an
    exemption.
    """
    compose_pins: dict[str, str] = {}
    for _var, _digest_var, image, default in compose_images:
        if DIGEST_RE.match(default) and default != PLACEHOLDER_DIGEST:
            compose_pins[image] = default

    problems: list[str] = []
    for number, ref in ci_images:
        if "@" not in ref:
            continue  # already reported as unpinned by check_ci_images
        name, _, digest = ref.rpartition("@")
        pinned = compose_pins.get(name)
        if pinned is not None and pinned != digest:
            problems.append(
                f"{CI_WORKFLOW.name} line {number}: {name} is pinned to {digest} in CI "
                f"but to {pinned} in {COMPOSE.name}\n"
                "    one image must carry one digest — refresh both with "
                "`python scripts/pin_digests.py --stdout`")
    return problems


def verify_remote(images, env_lines) -> int:
    """Ask each registry whether the pinned digest is still what the tag points at.

    `--check` proves a pin is shaped correctly; only the registry knows whether
    the tag has moved. A pin is not obliged to follow its tag — that is the point
    of pinning — so drift is a warning and still exits 0: a job that goes red
    because upstream rebuilt an image trains people to ignore it. An image that
    cannot be resolved at all does fail, because an unresolvable pin is the exact
    defect this file exists to catch, and "could not check" must never read as
    "checked". Network required, so this runs in the heavy CI tier, not on push.
    """
    present: dict[str, str] = {}
    for line in env_lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            present[k.strip()] = v.strip()

    effective: dict[str, str] = {}
    for _var, digest_var, image, default in images:
        value = present.get(digest_var) or default
        if DIGEST_RE.match(value) and value != PLACEHOLDER_DIGEST:
            effective[image] = value

    if CI_WORKFLOW.exists():
        for number, ref in parse_ci_images(CI_WORKFLOW.read_text(encoding="utf-8")):
            if "@" not in ref:
                continue
            name, _, digest = ref.rpartition("@")
            if DIGEST_RE.match(digest) and digest != PLACEHOLDER_DIGEST:
                effective.setdefault(name, digest)

    unreachable = 0
    drifted = 0
    for image, digest in sorted(effective.items()):
        try:
            actual = resolve_digest(image)
        except SystemExit as exc:
            print(f"FAIL {image}: {exc}", file=sys.stderr)
            unreachable += 1
            continue
        if actual != digest:
            print(
                f"WARN {image}: the tag now resolves to {actual}, this repo pins "
                f"{digest} — refresh deliberately with `python scripts/pin_digests.py`",
                file=sys.stderr)
            drifted += 1
        else:
            print(f"OK   {image} -> {digest}")

    if unreachable:
        print(
            f"\n{unreachable} image(s) could not be resolved against their registry"
            + (f" ({drifted} more drifted)" if drifted else ""),
            file=sys.stderr)
        return 1
    print(
        f"{len(effective)} image(s) checked against their registry: "
        f"{len(effective) - drifted} match the pin, {drifted} drifted"
    )
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


#: (ref, expected manifest URL). Each one is the exact shape that broke before
#: `manifest_url` existed: the tag doubled into the name segment, 404ing on
#: Docker Hub and failing token auth on quay.io. Offline — these are checked
#: on every run, in `--check` and the real resolve, because the real resolve
#: is also what `--check` cannot exercise (it needs a live registry) and this
#: bug shipped with a passing `--check` the whole time.
SELF_TEST_CASES = [
    ("redis:7-alpine", "https://registry-1.docker.io/v2/library/redis/manifests/7-alpine"),
    ("pgvector/pgvector:pg16", "https://registry-1.docker.io/v2/pgvector/pgvector/manifests/pg16"),
    ("quay.io/keycloak/keycloak:25.0", "https://quay.io/v2/keycloak/keycloak/manifests/25.0"),
    ("ollama/ollama:0.3.12", "https://registry-1.docker.io/v2/ollama/ollama/manifests/0.3.12"),
]


#: (workflow text, expected problem count). The CI-image half of the gate has
#: to be able to *fail*: a check that cannot fail is not a check. These cases
#: pin both directions — a pinned image passes, an unpinned one is reported,
#: and a malformed digest is not mistaken for a good one.
CI_IMAGE_SELF_TEST_CASES = [
    (
        "      redis:\n"
        "        image: redis:7-alpine@sha256:" + "a" * 64 + "\n",
        0,
    ),
    (
        "      redis:\n"
        "        image: redis:7-alpine\n",
        1,
    ),
    (
        "      postgres:\n"
        "        image: pgvector/pgvector:pg16@sha256:deadbeef\n",
        1,
    ),
    (
        "      postgres:\n"
        "        image: pgvector/pgvector:latest@sha256:" + "b" * 64 + "\n",
        1,
    ),
    (
        "      redis:\n"
        "        image: redis:7-alpine@sha256:" + "c" * 64 + "  # pinned\n",
        0,
    ),
    (
        # A comment mentioning `image:` must not be read as an image.
        "      # image: redis:7-alpine\n",
        0,
    ),
]


#: (Dockerfile text, expected base count). The base-image half of the gate has
#: to be able to *fail*, and it has to tell a base image apart from a build
#: stage: `FROM web AS run` names a stage this file already built, not an
#: image to pull, and treating it as one would demand a digest it cannot have.
DOCKERFILE_SELF_TEST_CASES = [
    (
        "FROM python:3.14-slim@sha256:" + "a" * 64 + "\n",
        1,
    ),
    (
        "FROM python:3.14-slim\n",
        1,
    ),
    (
        "FROM node:22-alpine@sha256:" + "b" * 64 + " AS web\n"
        "FROM python:3.14-slim@sha256:" + "c" * 64 + " AS run\n"
        "COPY --from=web /web/.next /web\n",
        2,
    ),
    (
        # A `FROM` that reuses an earlier stage is not a base image — it
        # cannot carry a digest and does not need one.
        "FROM node:22-alpine@sha256:" + "d" * 64 + " AS build\n"
        "FROM build AS run\n",
        1,
    ),
    (
        "# FROM python:3.14-slim\n",
        0,
    ),
]


#: (image, compose default digest, expected problem count). This half of the gate
#: was a bare `pass` in front of the exact case it exists to catch — every
#: compose service defaulted to the zero placeholder, so a fresh clone resolved
#: images that cannot be pulled while `--check` reported success. Both directions
#: are pinned here so it cannot quietly become a `pass` again.
COMPOSE_DEFAULT_SELF_TEST_CASES = [
    ("redis:7-alpine", PLACEHOLDER_DIGEST, 1),
    ("redis:7-alpine", "sha256:" + "a" * 64, 0),
    ("redis:7-alpine", "sha256:deadbeef", 1),
    ("redis:7-alpine", "", 1),
    ("redis:7-alpine", "latest", 1),
]

#: (compose images, CI image lines, expected problem count). One image must carry
#: one digest: compose and the workflow pinned `redis:7-alpine` to different
#: digests and every rule in this file passed, which meant CI was certifying an
#: image the shipped stack does not run.
PIN_CONSISTENCY_SELF_TEST_CASES = [
    (
        [("REDIS_IMAGE", "REDIS_DIGEST", "redis:7-alpine", "sha256:" + "a" * 64)],
        [(3, "redis:7-alpine@sha256:" + "a" * 64)],
        0,
    ),
    (
        [("REDIS_IMAGE", "REDIS_DIGEST", "redis:7-alpine", "sha256:" + "a" * 64)],
        [(3, "redis:7-alpine@sha256:" + "b" * 64)],
        1,
    ),
    (
        # An image named in only one file is nobody's business here; the
        # placeholder default is reported by check_compose_default instead.
        [("REDIS_IMAGE", "REDIS_DIGEST", "redis:7-alpine", PLACEHOLDER_DIGEST)],
        [(3, "quay.io/keycloak/keycloak:25.0@sha256:" + "b" * 64)],
        0,
    ),
]


def self_test() -> int:
    failures = []
    for ref, expected in SELF_TEST_CASES:
        actual = manifest_url(ref)
        if actual != expected:
            failures.append(f"{ref}: expected {expected!r}, got {actual!r}")
        # The one invariant that caught the original bug: the tag must appear
        # exactly once, after the final `/manifests/`, never inside the name.
        tag = ref.rpartition(":")[2]
        name_segment = actual.rsplit("/manifests/", 1)[0]
        if tag in name_segment.rsplit("/", 1)[-1]:
            failures.append(f"{ref}: tag {tag!r} leaked into the name segment of {actual!r}")
    for text, expected in CI_IMAGE_SELF_TEST_CASES:
        found = check_ci_images(text)
        if len(found) != expected:
            failures.append(
                f"CI image check: expected {expected} problem(s), got {len(found)} "
                f"for {text!r} -> {found}"
            )
    for text, expected in DOCKERFILE_SELF_TEST_CASES:
        found = parse_dockerfile_bases(text)
        if len(found) != expected:
            failures.append(
                f"Dockerfile base check: expected {expected} base image(s), got {len(found)} "
                f"for {text!r} -> {found}"
            )
    for image, default, expected in COMPOSE_DEFAULT_SELF_TEST_CASES:
        found = check_compose_default(image, default)
        if len(found) != expected:
            failures.append(
                f"compose default: expected {expected} problem(s), got {len(found)} "
                f"for {image!r} default {default!r} -> {found}"
            )
    for compose_images, ci_refs, expected in PIN_CONSISTENCY_SELF_TEST_CASES:
        found = check_pin_consistency(compose_images, ci_refs)
        if len(found) != expected:
            failures.append(
                f"pin consistency: expected {expected} problem(s), got {len(found)} "
                f"for compose={compose_images} ci={ci_refs} -> {found}"
            )
    for f in failures:
        print(f"SELF-TEST FAIL: {f}", file=sys.stderr)
    return len(failures)


def main() -> int:
    if self_test():
        print("pin_digests: self-test failed, refusing to run", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify only, no network")
    ap.add_argument("--stdout", action="store_true", help="print, change nothing")
    ap.add_argument(
        "--verify-remote", action="store_true",
        help="ask each registry whether the pinned digest still matches its tag")
    args = ap.parse_args()

    images = parse_compose_images(COMPOSE.read_text(encoding="utf-8"))
    if not images:
        print("error: no pinnable images found in docker-compose.yml", file=sys.stderr)
        return 2
    env_lines = read_env(ENV_FILE)

    if args.check:
        return check(images, env_lines)
    if args.verify_remote:
        return verify_remote(images, env_lines)

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
