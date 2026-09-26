"""ROOK-014: the compose policy (compose.py). A compose file is untrusted: dangerous keys are refused and
the rendered copy is hardened."""

import os
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from rook.sandbox.compose import ComposeError, Hardening, find_compose_file, render

LABELS = {"rook.run": "rook-x-abc123", "rook.sandbox": "1"}


def _write(ws: Path, doc: dict[str, Any] | str, name: str = "compose.yaml") -> Path:
    path = ws / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else yaml.safe_dump(doc))
    return path


def _render(
    ws: Path,
    doc: dict[str, Any] | str,
    *,
    service: str | None = None,
    env: dict[str, str] | None = None,
    host_port: int | None = None,
    read_only: bool = False,
) -> tuple[dict[str, Any], str]:
    path = _write(ws, doc)
    return render(
        path,
        ws,
        service=service,
        port=8000,
        host_port=host_port,
        env=env or {},
        hardening=Hardening(labels=LABELS, read_only=read_only),
    )


def _svc(**spec: Any) -> dict[str, Any]:
    return {"services": {"web": {"build": ".", **spec}}}


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"privileged": True}, "privileged"),
        ({"network_mode": "host"}, "network_mode"),
        ({"pid": "host"}, "pid"),
        ({"ipc": "host"}, "ipc"),
        ({"uts": "host"}, "uts"),
        ({"userns_mode": "host"}, "userns_mode"),
        ({"cap_add": ["SYS_ADMIN"]}, "cap_add"),
        ({"devices": ["/dev/sda:/dev/sda"]}, "devices"),
        ({"security_opt": ["seccomp:unconfined"]}, "security_opt"),
        ({"cgroup_parent": "x"}, "cgroup_parent"),
        ({"volumes_from": ["other"]}, "volumes_from"),
        ({"extends": {"file": "/etc/other.yml", "service": "x"}}, "extends"),
        ({"sysctls": {"net.core.somaxconn": 1024}}, "sysctls"),
        ({"ulimits": {"nproc": 65535}}, "ulimits"),
        ({"runtime": "runc"}, "runtime"),
        ({"group_add": ["999"]}, "group_add"),
        ({"gpus": "all"}, "gpus"),
        ({"secrets": ["key"]}, "secrets"),
    ],
)
def test_dangerous_service_keys_are_refused(tmp_path: Path, spec: dict[str, Any], message: str) -> None:
    with pytest.raises(ComposeError, match=message):
        _render(tmp_path, _svc(**spec))


@pytest.mark.parametrize(
    "volume",
    [
        "/:/host",
        "/var/run/docker.sock:/var/run/docker.sock",
        "~/.ssh:/root/.ssh",
        "../outside:/data",
        "${HOME}:/home",
        "$PWD/..:/x",
        "undeclared:/data",
        {"type": "bind", "source": "/etc", "target": "/etc"},
        {"type": "volume", "source": "/etc", "target": "/etc"},
        {"type": "npipe", "source": "x", "target": "/x"},
        {"type": "bind", "source": ".", "target": "/x", "bind": {"propagation": "rshared"}},
    ],
)
def test_host_mounts_outside_the_workspace_are_refused(tmp_path: Path, volume: Any) -> None:
    with pytest.raises(ComposeError):
        _render(tmp_path, _svc(volumes=[volume]))


def test_symlink_escaping_the_workspace_is_refused(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink("/etc", ws / "etc-link")
    with pytest.raises(ComposeError, match="inside the workspace"):
        _render(ws, _svc(volumes=["./etc-link:/x"]))
    with pytest.raises(ComposeError, match="inside the workspace"):
        _render(ws, {"services": {"web": {"build": "etc-link"}}})


def test_mounts_inside_the_workspace_are_allowed_as_absolute_paths(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    doc, _ = _render(
        tmp_path,
        {
            **_svc(
                volumes=[
                    "./data:/data:ro",
                    "cache:/cache",
                    "/anon",
                    {"type": "tmpfs", "target": "/t"},
                    {"type": "bind", "source": "./data", "target": "/d2"},
                ]
            ),
            "volumes": {"cache": None},
        },
    )
    volumes = doc["services"]["web"]["volumes"]
    assert volumes[0] == f"{tmp_path.resolve()}/data:/data:ro"
    assert volumes[1:3] == ["cache:/cache", "/anon"]
    assert volumes[4]["source"] == str((tmp_path / "data").resolve())
    assert doc["volumes"]["cache"]["labels"] == LABELS


@pytest.mark.parametrize(
    "build",
    [
        "..",
        "/",
        "https://github.com/evil/repo.git",
        "${HOME}",
        {"context": ".", "dockerfile": "../../Dockerfile"},
        {"context": ".", "network": "host"},
        {"context": ".", "secrets": ["key"]},
        {"context": ".", "ssh": ["default"]},
        {"context": ".", "additional_contexts": {"x": "/"}},
        {"context": ".", "privileged": True},
    ],
)
def test_build_must_stay_in_the_workspace(tmp_path: Path, build: Any) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ComposeError):
        _render(ws, {"services": {"web": {"build": build}}})


@pytest.mark.parametrize(
    "env_file", ["/home/user/.bob-key.env", "../.env", "~/.env", "${HOME}/.env", [{"path": "/etc/passwd"}]]
)
def test_env_files_must_be_in_the_workspace(tmp_path: Path, env_file: Any) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ComposeError):
        _render(ws, _svc(env_file=env_file))


@pytest.mark.parametrize(
    "doc",
    [
        {"services": {"web": {"build": "."}}, "include": ["/etc/other.yml"]},
        {"services": {"web": {"build": "."}}, "secrets": {"k": {"file": "/home/u/.ssh/id_rsa"}}},
        {"services": {"web": {"build": "."}}, "configs": {"c": {"file": "/etc/shadow"}}},
        {
            "services": {"web": {"build": "."}},
            "volumes": {"v": {"driver_opts": {"device": "/", "o": "bind"}}},
        },
        {"services": {"web": {"build": "."}}, "volumes": {"v": {"external": True}}},
        {"services": {"web": {"build": "."}}, "volumes": {"v": {"name": "someone-elses-db"}}},
        {"services": {}},
        {"services": {"web": {"command": "x"}}},
        "services: [unclosed",
        "- a list",
    ],
)
def test_bad_top_level_documents_are_refused(tmp_path: Path, doc: Any) -> None:
    with pytest.raises(ComposeError):
        _render(tmp_path, doc)


def test_rendered_services_are_hardened(tmp_path: Path) -> None:
    doc, app = _render(
        tmp_path,
        {
            "services": {
                "web": {
                    "build": ".",
                    "ports": ["0.0.0.0:8000:8000", "9229:9229"],
                    "container_name": "fixed",
                    "restart": "always",
                    "deploy": {"resources": {"limits": {"memory": "64g"}}},
                    "networks": ["front"],
                    "mem_limit": "64g",
                    "user": "root",
                    "labels": {"rook.run": "spoof"},
                    "environment": ["A=1", "B=2"],
                },
                "db": {"image": "postgres:16-alpine", "ports": ["5432:5432"], "user": "999:999"},
            },
            "networks": {"front": {"driver": "host"}},
        },
        service="web",
        env={"TOKEN": "a$b"},
        read_only=True,
    )
    assert app == "web"
    web, db = doc["services"]["web"], doc["services"]["db"]
    assert "ports" not in web and "ports" not in db  # only the proxy publishes
    proxy = doc["services"]["rook-proxy"]
    assert proxy["ports"] == ["127.0.0.1::8080"]
    alias = proxy["command"][-2]
    assert alias.startswith("rook-app-") and proxy["command"][-1] == "8000"
    assert web["networks"] == {"default": {"aliases": [alias]}}
    assert proxy["networks"] == ["default", "rook-publish"]
    assert proxy["cap_drop"] == ["ALL"] and proxy["read_only"] is True and proxy["user"] == "65534:65534"
    assert proxy["labels"] == LABELS
    for svc in (web, db):
        assert svc["cap_drop"] == ["ALL"] and "cap_add" not in svc
        assert svc["security_opt"] == ["no-new-privileges:true"]
        assert svc["pids_limit"] == 512 and svc["mem_limit"] == "2g" and svc["cpus"] == 2.0
        assert svc["restart"] == "no" and svc["init"] is True
        assert svc["labels"]["rook.run"] == "rook-x-abc123"
        assert svc["read_only"] is True and any(t.startswith("/tmp:") for t in svc["tmpfs"])
        for key in ("container_name", "deploy", "network_mode", "privileged", "hostname", "domainname"):
            assert key not in svc
    assert "networks" not in db
    assert web["user"] == "10001:10001"  # root is replaced
    assert db["user"] == "999:999"  # numeric non-root is kept
    assert web["environment"] == {"A": "1", "B": "2", "TOKEN": "a$$b"}  # plan env is not interpolated
    assert web["build"]["context"] == str(tmp_path.resolve())
    assert web["build"]["labels"]["rook.run"] == "rook-x-abc123"
    assert doc["networks"] == {
        "default": {
            "internal": True,
            "driver_opts": {"com.docker.network.bridge.inhibit_ipv4": "true"},
            "labels": LABELS,
        },
        "rook-publish": {"labels": LABELS},
    }


def test_restart_reuses_the_host_port(tmp_path: Path) -> None:
    doc, _ = _render(tmp_path, _svc(), host_port=41000)
    assert doc["services"]["rook-proxy"]["ports"] == ["127.0.0.1:41000:8080"]


def test_app_service_selection(tmp_path: Path) -> None:
    two = {"services": {"api": {"build": ".", "ports": ["8000:8000"]}, "db": {"image": "postgres:16-alpine"}}}
    assert _render(tmp_path, two)[1] == "api"  # the only one publishing the plan's port
    assert _render(tmp_path, two, service="db")[1] == "db"
    three = {"services": {"a": {"build": "."}, "b": {"build": "."}}}
    with pytest.raises(ComposeError, match="which service"):
        _render(tmp_path, three)


def test_find_compose_file(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="no compose file"):
        find_compose_file(tmp_path, None)
    root = _write(tmp_path, "services: {}", "docker-compose.yml")
    assert find_compose_file(tmp_path, None) == root.resolve()
    ours = _write(tmp_path, "services: {}", ".rook-sandbox/compose.yaml")
    assert find_compose_file(tmp_path, "docker compose up --build") == ours.resolve()
    assert find_compose_file(tmp_path, "docker-compose.yml") == root.resolve()
    with pytest.raises(ComposeError, match="inside the workspace"):
        find_compose_file(tmp_path, "../../etc/compose.yml")
    with pytest.raises(ComposeError, match="not found"):
        find_compose_file(tmp_path, "missing.yml")


def test_huge_compose_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="too large"):
        _render(tmp_path, "x: " + "a" * 1_100_000)


def test_yaml_tags_cannot_run_code(tmp_path: Path) -> None:
    evil = textwrap.dedent(
        """
        services:
          web: !!python/object/apply:os.system ["touch pwned"]
        """
    )
    with pytest.raises(ComposeError, match="not valid YAML"):
        _render(tmp_path, evil)
    assert not (tmp_path / "pwned").exists()


def test_the_proxy_service_name_is_reserved(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="reserved"):
        _render(tmp_path, {"services": {"web": {"build": "."}, "rook-proxy": {"image": "evil"}}})


def test_yaml_alias_bombs_are_refused(tmp_path: Path) -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]" for i in range(1, 9)]
    bomb = "x-bomb:\n" + "\n".join("  " + line for line in lines) + "\nservices:\n  web: {build: .}\n"
    with pytest.raises(ComposeError, match="too many nodes"):
        _render(tmp_path, bomb)


def test_normal_anchors_still_work(tmp_path: Path) -> None:
    doc = "x-common: &common {environment: {A: '1'}}\nservices:\n  web: {<<: *common, build: .}\n"
    rendered, _ = _render(tmp_path, doc)
    assert rendered["services"]["web"]["environment"] == {"A": "1"}


def test_no_other_service_can_claim_the_apps_dns_name(tmp_path: Path) -> None:
    doc, app = _render(
        tmp_path,
        {
            "services": {
                "web": {"build": ".", "hostname": "web", "domainname": "local"},
                "evil": {
                    "image": "python:3.12-slim",
                    "hostname": "web",
                    "domainname": "local",
                    "container_name": "web",
                    "networks": {"default": {"aliases": ["web", "rook-app-00000000"]}},
                },
            }
        },
        service="web",
    )
    assert app == "web"
    evil = doc["services"]["evil"]
    for key in ("hostname", "domainname", "container_name", "networks"):
        assert key not in evil
    alias = doc["services"]["rook-proxy"]["command"][-2]
    owners = [n for n, svc in doc["services"].items() if alias in str(svc.get("networks", ""))]
    assert owners == ["web"]
    # A fresh random alias per render, so a compose file cannot guess it.
    assert _render(tmp_path, _svc())[0]["services"]["rook-proxy"]["command"][-2] != alias


@pytest.mark.parametrize("key", ["links", "external_links"])
def test_links_are_refused(tmp_path: Path, key: str) -> None:
    doc = {"services": {"web": {"build": "."}, "evil": {"image": "x", key: ["web:web"]}}}
    with pytest.raises(ComposeError, match=key):
        _render(tmp_path, doc, service="web")


def test_rook_service_names_are_reserved(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="reserved"):
        _render(tmp_path, {"services": {"web": {"build": "."}, "rook-app-1234abcd": {"image": "x"}}})
