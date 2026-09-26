"""The run-phase network layout of DockerSandbox: an internal app network plus a tiny port proxy.

03 section 3: the app's network must be limited to the sandbox at run time. The app therefore runs only
on an `--internal` bridge created with `inhibit_ipv4`: no route out (no internet, no cloud metadata) and
no host address on the bridge (no host services), but containers on it still reach each other by name.

Docker cannot publish a port from an internal network, so a proxy container, which Rook writes and
controls, joins both the internal network and a normal "publish" network. It is published on
127.0.0.1 and only forwards TCP to `<app alias>:<port>`. It runs from an image Rook already uses (the
Python base image), as nobody, with no capabilities, a read-only root filesystem and small limits.
"""

import textwrap
from collections.abc import Mapping

PROXY_IMAGE = "python:3.12-slim"
PROXY_PORT = 8080
PROXY_USER = "65534:65534"  # nobody
APP_ALIAS = "app"
INTERNAL_NETWORK_OPTS = {"com.docker.network.bridge.inhibit_ipv4": "true"}

# argv: <listen port> <target host> <target port>. Pure stdlib; forwards bytes both ways.
PROXY_SCRIPT = textwrap.dedent(
    """
    import asyncio, sys

    LISTEN, HOST, PORT = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    MAX_CONNECTIONS = 256
    active = 0

    async def pipe(reader, writer):
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
            if writer.can_write_eof():
                writer.write_eof()
        except (OSError, asyncio.IncompleteReadError):
            pass

    async def handle(client_r, client_w):
        global active
        if active >= MAX_CONNECTIONS:
            client_w.close()
            return
        active += 1
        try:
            try:
                app_r, app_w = await asyncio.open_connection(HOST, PORT)
            except OSError:
                return
            try:
                await asyncio.gather(pipe(client_r, app_w), pipe(app_r, client_w))
            finally:
                app_w.close()
        finally:
            active -= 1
            client_w.close()

    async def main():
        server = await asyncio.start_server(handle, "0.0.0.0", LISTEN)
        async with server:
            await server.serve_forever()

    asyncio.run(main())
    """
)


def proxy_command(target_host: str, target_port: int) -> list[str]:
    return ["python", "-c", PROXY_SCRIPT, str(PROXY_PORT), target_host, str(target_port)]


def proxy_run_argv(
    *, name: str, network: str, host_port: int | None, target_port: int, labels: Mapping[str, str]
) -> list[str]:
    """`docker run` argv for the proxy (attached to the publish network; the internal one is added after)."""
    argv = [
        "run", "-d",
        "--name", name,
        "--network", network,
        "--publish", f"127.0.0.1:{host_port or ''}:{PROXY_PORT}",
        "--user", PROXY_USER,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--read-only",
        "--pids-limit", "64",
        "--memory", "128m",
        "--memory-swap", "128m",
        "--cpus", "0.5",
        "--init",
        "--restart", "no",
        "--log-driver", "json-file",
        "--log-opt", "max-size=1m",
        "--log-opt", "max-file=1",
    ]  # fmt: skip
    for key, value in labels.items():
        argv += ["--label", f"{key}={value}"]
    return [*argv, PROXY_IMAGE, *proxy_command(APP_ALIAS, target_port)]
