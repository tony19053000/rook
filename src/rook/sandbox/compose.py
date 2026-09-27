"""Checks a project's compose file and renders the hardened copy that DockerSandbox actually runs.

The compose file comes from the target repo or from the Mechanic (Bob), so it is untrusted. This is an
allowlist: a service may only use the keys in `_SERVICE_KEYS`. Keys that would weaken the sandbox
(privileged, host namespaces, extra capabilities, devices, security_opt, ...) are refused with a clear
error the Mechanic can act on; keys the sandbox owns (ports, networks, resources, logging, restart,
container names) are dropped and set by Rook instead.

What is supported, in short:
- `image` and `build` services (build context and Dockerfile must be inside the workspace copy);
- named and anonymous volumes (no driver, driver_opts, external or name), tmpfs, and bind mounts whose
  source resolves inside the workspace copy (the only host path a sandbox may mount, 03 section 3);
- `env_file`s inside the workspace; `environment`, `command`, `entrypoint`, `healthcheck`, `depends_on`;
- all services share one internal project network with no host address (user-defined networks are
  dropped), so at run time they reach each other but not the internet or the host. Nothing is published
  except Rook's proxy service (proxy.py), on 127.0.0.1, which forwards to the app service.

Paths may not use `${...}` interpolation, so a path cannot be pointed at the host after it was checked.
"""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from rook.sandbox.proxy import (
    INTERNAL_NETWORK_OPTS,
    PROXY_IMAGE,
    PROXY_PORT,
    PROXY_USER,
    proxy_command,
)

MAX_COMPOSE_BYTES = 1_000_000
# YAML aliases can make a small file expand into a huge document ("billion laughs"): cap the node count.
MAX_COMPOSE_NODES = 50_000
PROXY_SERVICE = "rook-proxy"
_PUBLISH_NETWORK = "rook-publish"
COMPOSE_NAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

_SERVICE_KEYS = frozenset(
    {
        "image",
        "build",
        "command",
        "entrypoint",
        "environment",
        "env_file",
        "working_dir",
        "user",
        "depends_on",
        "healthcheck",
        "expose",
        "volumes",
        "tmpfs",
        "labels",
        "stop_signal",
        "stop_grace_period",
        "init",
        "tty",
        "read_only",
        "shm_size",
        "platform",
        "pull_policy",
        "profiles",
        "extra_hosts",
        "dns",
        "dns_search",
        "annotations",
    }
)
# Set by Rook for every service; whatever the file says is ignored.
_DROPPED_SERVICE_KEYS = frozenset(
    {
        "ports",
        "networks",
        "container_name",
        # A second service could claim the app's DNS name with these (the proxy would round-robin).
        "hostname",
        "domainname",
        "restart",
        "deploy",
        "logging",
        "stdin_open",
        "mem_limit",
        "memswap_limit",
        "mem_reservation",
        "mem_swappiness",
        "cpus",
        "cpu_count",
        "cpu_percent",
        "cpu_shares",
        "cpu_quota",
        "cpu_period",
        "cpuset",
        "pids_limit",
        "oom_score_adj",
        "scale",
    }
)
_BUILD_KEYS = frozenset({"context", "dockerfile", "dockerfile_inline", "args", "target", "labels"})
_TOP_KEYS = frozenset({"services", "volumes", "networks", "name", "version"})
_VOLUME_KEYS = frozenset({"type", "source", "target", "read_only", "volume", "bind", "tmpfs", "consistency"})


class ComposeError(ValueError):
    """The compose file uses something the sandbox does not allow."""


@dataclass(frozen=True, slots=True)
class Hardening:
    """What DockerSandbox enforces on every service (03 section 3)."""

    user: str = "10001:10001"
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 512
    read_only: bool = False
    tmpfs_size: str = "256m"
    labels: Mapping[str, str] = field(default_factory=dict)


def find_compose_file(workspace: Path, hint: str | None) -> Path:
    """The compose file to use: `hint` if it names a file in the workspace, else the usual names."""
    root = workspace.resolve()
    if hint and hint.strip().endswith((".yml", ".yaml")):
        path = inside(root, root / hint.strip(), "compose file")
        if not path.is_file():
            raise ComposeError(f"compose file {hint!r} not found in the workspace")
        return path
    for folder in (root / ".rook-sandbox", root):
        for name in COMPOSE_NAMES:
            if (folder / name).is_file():
                return inside(root, folder / name, "compose file")
    raise ComposeError("no compose file found (compose.yaml / docker-compose.yml)")


def inside(root: Path, path: Path, what: str) -> Path:
    """`path` resolved (symlinks followed); ComposeError unless it is inside `root`."""
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ComposeError(f"{what} must be inside the workspace copy: {path}")
    return resolved


def _no_interpolation(value: str, what: str) -> str:
    if not isinstance(value, str) or "$" in value or "\x00" in value:
        raise ComposeError(f"{what} must be a plain string without '$' interpolation: {value!r}")
    return value


def _labels(value: Any, what: str) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): "" if v is None else str(v) for k, v in value.items()}
    if isinstance(value, list):
        out = {}
        for item in value:
            key, _, val = str(item).partition("=")
            out[key] = val
        return out
    raise ComposeError(f"{what} labels must be a mapping or a list")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


@dataclass
class _Checker:
    root: Path  # the workspace copy, resolved
    base: Path  # the compose file's folder: relative paths are relative to it
    volumes: set[str]

    def path(self, value: Any, what: str) -> str:
        raw = _no_interpolation(value, what)
        if raw.startswith("~"):
            raise ComposeError(f"{what} may not use '~': {raw!r}")
        return str(inside(self.root, self.base / raw, what))

    def build(self, svc: str, value: Any, labels: Mapping[str, str]) -> dict[str, Any]:
        spec = {"context": value} if isinstance(value, str) else value
        if not isinstance(spec, dict):
            raise ComposeError(f"service {svc!r}: build must be a path or a mapping")
        bad = sorted(set(spec) - _BUILD_KEYS)
        if bad:
            raise ComposeError(f"service {svc!r}: build keys not allowed in the sandbox: {bad}")
        out = dict(spec)
        context_raw = _no_interpolation(spec.get("context", "."), f"service {svc!r} build context")
        if "://" in context_raw or context_raw.startswith("git@"):
            raise ComposeError(f"service {svc!r}: the build context must be a folder in the workspace")
        context = self.path(context_raw, f"service {svc!r} build context")
        out["context"] = context
        if "dockerfile" in spec:
            name = _no_interpolation(spec["dockerfile"], f"service {svc!r} dockerfile")
            out["dockerfile"] = str(inside(self.root, Path(context) / name, f"service {svc!r} dockerfile"))
        out["labels"] = {**_labels(spec.get("labels"), f"service {svc!r} build"), **labels}
        return out

    def volume(self, svc: str, value: Any) -> Any:
        what = f"service {svc!r} volume"
        if isinstance(value, str):
            spec = _no_interpolation(value, what)
            parts = spec.split(":")
            if len(parts) == 1:  # anonymous volume: a container path only
                return spec
            if len(parts) > 3:
                raise ComposeError(f"{what} {spec!r} is not 'source:target[:mode]'")
            source, rest = parts[0], parts[1:]
            if source.startswith(("/", ".", "~")):
                return ":".join([self.path(source, what), *rest])
            if source not in self.volumes:
                raise ComposeError(f"{what} {source!r} is not a named volume declared in the file")
            return spec
        if not isinstance(value, dict):
            raise ComposeError(f"{what} must be a string or a mapping")
        bad = sorted(set(value) - _VOLUME_KEYS)
        if bad:
            raise ComposeError(f"{what}: keys not allowed: {bad}")
        kind = value.get("type", "volume")
        out = dict(value)
        if kind == "bind":
            if isinstance(value.get("bind"), dict) and set(value["bind"]) - {"create_host_path", "selinux"}:
                raise ComposeError(f"{what}: bind options not allowed: {sorted(value['bind'])}")
            out["source"] = self.path(value.get("source", ""), what)
        elif kind == "volume":
            source = value.get("source")
            if source is not None and _no_interpolation(source, what) not in self.volumes:
                raise ComposeError(f"{what} {source!r} is not a named volume declared in the file")
        elif kind != "tmpfs":
            raise ComposeError(f"{what}: type {kind!r} is not allowed (bind, volume or tmpfs only)")
        return out

    def env_file(self, svc: str, value: Any) -> list[Any]:
        out: list[Any] = []
        for item in _as_list(value):
            if isinstance(item, dict):
                out.append({**item, "path": self.path(item.get("path", ""), f"service {svc!r} env_file")})
            else:
                out.append(self.path(item, f"service {svc!r} env_file"))
        return out


def _user(value: Any, default: str) -> str:
    """Keep a numeric, non-root `uid[:gid]`; anything else (names, root, empty) runs as `default`."""
    uid, _, gid = str(value if value is not None else "").partition(":")
    if uid.isdigit() and int(uid) != 0 and (not gid or (gid.isdigit() and int(gid) != 0)):
        return f"{uid}:{gid}" if gid else uid
    return default


def _escape(env: Mapping[str, str]) -> dict[str, str]:
    return {k: v.replace("$", "$$") for k, v in env.items()}


def render(
    compose_path: Path,
    workspace: Path,
    *,
    service: str | None,
    port: int,
    host_port: int | None,
    env: Mapping[str, str],
    hardening: Hardening,
    access_network: str | None = None,
    access_alias: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Check the compose file and return `(hardened compose document, app service name)`.

    `env` (the plan's values) is added to the app service's environment. Only Rook's proxy service is
    reachable: published on 127.0.0.1 (`host_port` or a Docker-picked one), or, with `access_network`
    (Rook itself runs in a container on that existing network), not published at all but joined to that
    network as `access_alias`.
    """
    root = workspace.resolve()
    compose_path = inside(root, compose_path, "compose file")
    raw = compose_path.read_bytes()
    if len(raw) > MAX_COMPOSE_BYTES:
        raise ComposeError("compose file is too large")
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ComposeError(f"compose file is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("services"), dict) or not doc["services"]:
        raise ComposeError("compose file needs a non-empty 'services' mapping")
    bad = sorted(k for k in doc if k not in _TOP_KEYS and not str(k).startswith("x-"))
    if bad:
        raise ComposeError(f"top-level compose keys not allowed in the sandbox: {bad}")

    volumes_in = doc.get("volumes") or {}
    if not isinstance(volumes_in, dict):
        raise ComposeError("top-level volumes must be a mapping")
    volumes_out: dict[str, Any] = {}
    for name, spec in volumes_in.items():
        extra = sorted(set(spec or {}) - {"labels"}) if isinstance(spec, dict) or spec is None else ["?"]
        if extra:
            raise ComposeError(f"volume {name!r}: only plain named volumes are allowed, not {extra}")
        volumes_out[str(name)] = {
            "labels": {**_labels((spec or {}).get("labels"), "volume"), **hardening.labels}
        }

    _check_size(doc)
    services: dict[str, Any] = doc["services"]
    reserved = sorted(str(n) for n in services if str(n).startswith("rook-"))
    if reserved:
        raise ComposeError(f"service names starting with 'rook-' are reserved for the sandbox: {reserved}")
    app = _pick_service(services, service, port)
    check = _Checker(root, compose_path.parent, set(volumes_out))
    rendered: dict[str, Any] = {}
    for name, spec in services.items():
        rendered[str(name)] = _service(check, str(name), spec, hardening)
    app_spec = rendered[app]
    app_env = app_spec.get("environment") or {}
    if isinstance(app_env, list):
        app_env = dict(str(e).partition("=")[::2] for e in app_env)
    app_spec["environment"] = {**app_env, **_escape(env)}

    # The proxy targets a random alias that only the picked app service gets: no other service can own
    # it (their hostname, domainname, container_name, networks and aliases are dropped; links refused).
    app_alias = f"rook-app-{secrets.token_hex(4)}"
    app_spec["networks"] = {"default": {"aliases": [app_alias]}}
    proxy = _proxy_service(app_alias, port, host_port, hardening)
    publish_network: dict[str, Any] = {"labels": dict(hardening.labels)}
    if access_network is not None:
        del proxy["ports"]
        proxy["networks"] = {"default": {}, _PUBLISH_NETWORK: {"aliases": [access_alias or PROXY_SERVICE]}}
        publish_network = {"external": True, "name": access_network}
    rendered[PROXY_SERVICE] = proxy
    out: dict[str, Any] = {
        "services": rendered,
        "networks": {
            "default": {
                "internal": True,
                "driver_opts": dict(INTERNAL_NETWORK_OPTS),
                "labels": dict(hardening.labels),
            },
            _PUBLISH_NETWORK: publish_network,
        },
    }
    if volumes_out:
        out["volumes"] = volumes_out
    return out, app


def _check_size(doc: Any) -> None:
    """Walk the document as compose would see it (aliases expanded) and stop past MAX_COMPOSE_NODES."""
    stack, seen = [doc], 0
    while stack:
        node = stack.pop()
        seen += 1
        if seen > MAX_COMPOSE_NODES:
            raise ComposeError("compose file expands to too many nodes (YAML alias bomb?)")
        if isinstance(node, dict):
            stack.extend(node.keys())
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _proxy_service(target: str, port: int, host_port: int | None, h: Hardening) -> dict[str, Any]:
    """Rook's own forwarder: the only published service, on 127.0.0.1 (see proxy.py)."""
    return {
        "image": PROXY_IMAGE,
        "command": proxy_command(target, port),
        "networks": ["default", _PUBLISH_NETWORK],
        "ports": [f"127.0.0.1:{host_port or ''}:{PROXY_PORT}"],
        "user": PROXY_USER,
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": 64,
        "mem_limit": "128m",
        "memswap_limit": "128m",
        "cpus": 0.5,
        "init": True,
        "restart": "no",
        "labels": dict(h.labels),
        "logging": {"driver": "json-file", "options": {"max-size": "1m", "max-file": "1"}},
    }


def _pick_service(services: Mapping[str, Any], wanted: str | None, port: int) -> str:
    names = [str(n) for n in services]
    if wanted and wanted.strip() in names:
        return wanted.strip()
    if len(names) == 1:
        return names[0]
    publishing = [
        n
        for n, spec in services.items()
        if isinstance(spec, dict)
        and any(str(p).split(":")[-1].split("/")[0] == str(port) for p in _as_list(spec.get("ports")))
    ]
    if len(publishing) == 1:
        return str(publishing[0])
    raise ComposeError(
        f"cannot tell which service serves port {port}; set the plan's start to one of {names}"
    )


def _service(check: _Checker, name: str, spec: Any, h: Hardening) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ComposeError(f"service {name!r} must be a mapping")
    bad = sorted(
        k
        for k in spec
        if k not in _SERVICE_KEYS and k not in _DROPPED_SERVICE_KEYS and not str(k).startswith("x-")
    )
    if bad:
        raise ComposeError(f"service {name!r} uses keys not allowed in the sandbox: {bad}")
    if "image" not in spec and "build" not in spec:
        raise ComposeError(f"service {name!r} needs an image or a build")
    out = {k: v for k, v in spec.items() if k in _SERVICE_KEYS}
    if "build" in spec:
        out["build"] = check.build(name, spec["build"], h.labels)
    if "volumes" in spec:
        out["volumes"] = [check.volume(name, v) for v in _as_list(spec["volumes"])]
    if "env_file" in spec:
        out["env_file"] = check.env_file(name, spec["env_file"])
    out["user"] = _user(spec.get("user"), h.user)
    out["labels"] = {**_labels(spec.get("labels"), f"service {name!r}"), **h.labels}
    out["cap_drop"] = ["ALL"]
    out["security_opt"] = ["no-new-privileges:true"]
    out["pids_limit"] = h.pids
    out["mem_limit"] = h.memory
    out["memswap_limit"] = h.memory
    out["cpus"] = h.cpus
    out["restart"] = "no"
    out["init"] = True
    out["logging"] = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "1"}}
    if h.read_only:
        out["read_only"] = True
        out["tmpfs"] = [*_as_list(spec.get("tmpfs")), f"/tmp:rw,nosuid,nodev,size={h.tmpfs_size}"]
    return out
