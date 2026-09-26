# syntax=docker/dockerfile:1
# The hosted Rook server (02 §14): FastAPI on uvicorn, the allowlisted demo apps and their Bob recordings.
# Build from the repo root:  docker build -f deploy/Dockerfile -t rook-server .
#
# Bob Shell is never committed (licence unknown). `deploy/pack-bob.sh` packs the locally installed Bob into the
# gitignored deploy/vendor/; without it the image still builds and serves replay mode only (start.sh says so).
FROM python:3.12-slim-bookworm

ARG NODE22_VERSION=22.23.3
ARG NODE22_SHA256=df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de
ARG NODE24_VERSION=24.21.0
ARG NODE24_SHA256=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6
ARG GO_VERSION=1.27.1
ARG GO_SHA256=63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445
ARG BOB_VERSION=2.0.5

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git tini xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Node 22 is the default `node` (JS demo apps) and Go builds Go demo apps. Node 24 runs only Bob Shell, so it is
# installed with Bob below. Tarballs are checked against pinned SHA-256 sums.
RUN fetch() { curl -fsSL --proto '=https' --tlsv1.2 -o "$1" "$2" && echo "$3  $1" | sha256sum -c -; } \
    && fetch /tmp/node22.tar.xz "https://nodejs.org/dist/v${NODE22_VERSION}/node-v${NODE22_VERSION}-linux-x64.tar.xz" "${NODE22_SHA256}" \
    && fetch /tmp/go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" "${GO_SHA256}" \
    && mkdir -p /opt/node22 \
    && tar -xJf /tmp/node22.tar.xz -C /opt/node22 --strip-components=1 --no-same-owner \
    && tar -xzf /tmp/go.tar.gz -C /usr/local --no-same-owner \
    && rm -rf /tmp/node22.tar.xz /tmp/go.tar.gz /opt/node22/include /opt/node22/share /usr/local/go/test /usr/local/go/api \
    && ln -s /opt/node22/bin/node /opt/node22/bin/npm /opt/node22/bin/npx /usr/local/bin/ \
    && node --version && /usr/local/go/bin/go version

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv

# The server runs as `rook`; everything it does not need to write stays root-owned.
RUN useradd --create-home --home-dir /home/rook --uid 10001 --user-group --shell /usr/sbin/nologin rook \
    && mkdir -p /data /opt/rook/config /opt/rook/demos \
    && chown rook:rook /data

ENV PATH=/app/.venv/bin:/usr/local/go/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable && rm -rf /root/.cache/uv

# Optional Bob Shell (deploy/vendor/bobshell-<version>.tgz, see deploy/vendor/README.md) and its Node 24.
COPY deploy/vendor/ /tmp/vendor/
RUN tgz="/tmp/vendor/bobshell-${BOB_VERSION}.tgz"; \
    if [ -f "$tgz" ]; then \
        if [ -f "$tgz.sha256" ]; then (cd /tmp/vendor && sha256sum -c "bobshell-${BOB_VERSION}.tgz.sha256"); fi; \
        curl -fsSL --proto '=https' --tlsv1.2 -o /tmp/node24.tar.xz \
            "https://nodejs.org/dist/v${NODE24_VERSION}/node-v${NODE24_VERSION}-linux-x64.tar.xz" \
        && echo "${NODE24_SHA256}  /tmp/node24.tar.xz" | sha256sum -c - \
        && mkdir -p /opt/node24 /opt/bobshell \
        && tar -xJf /tmp/node24.tar.xz -C /opt/node24 --strip-components=1 --no-same-owner \
        && rm -rf /tmp/node24.tar.xz /opt/node24/include /opt/node24/share \
        && tar -xzf "$tgz" -C /opt/bobshell --strip-components=1 --no-same-owner \
        && version="$(/opt/node24/bin/node -p 'require("/opt/bobshell/package.json").version')" \
        && if [ "$version" != "${BOB_VERSION}" ]; then echo "vendored Bob is $version, expected ${BOB_VERSION}" >&2; exit 1; fi \
        && printf '#!/bin/sh\nexec /opt/node24/bin/node /opt/bobshell/dist/bob.js "$@"\n' > /usr/local/bin/bob \
        && chmod 755 /usr/local/bin/bob \
        && echo "Bob Shell ${BOB_VERSION} on Node ${NODE24_VERSION} installed: live mode available"; \
    else \
        echo "NOTE: no deploy/vendor/bobshell-${BOB_VERSION}.tgz: building a REPLAY-ONLY image (no Bob Shell, no Node 24)"; \
    fi; \
    rm -rf /tmp/vendor

# Demo apps from pinned SHAs (deploy/demos/repos.txt, ROOK-039), then the interim demo: the minishop fixture.
COPY deploy/demos/ /opt/rook/config/
RUN /opt/rook/config/build-demos.sh /opt/rook/config/repos.txt /opt/rook/demos
COPY tests/fixtures/minishop/app.py tests/fixtures/minishop/test_minishop_app.py /opt/rook/demos/minishop/

# Bob recordings of our own demo apps only (03 §10), read by replay mode from $HOME/.rook/recordings.
COPY tests/fixtures/recordings/understand_minishop/ tests/fixtures/recordings/rules_minishop/ \
     tests/fixtures/recordings/design_minishop/ tests/fixtures/recordings/diagnose_minishop/ \
     tests/fixtures/recordings/surgeon_minishop/ tests/fixtures/recordings/session_minishop/ \
     /home/rook/.rook/recordings/
RUN chown rook:rook /home/rook/.rook && chmod -R a+rX /home/rook/.rook/recordings /opt/rook

COPY deploy/start.sh /usr/local/bin/rook-start
RUN chmod 755 /usr/local/bin/rook-start

ENV HOME=/home/rook \
    PORT=8000 \
    ROOK_BOB_MODE=replay \
    ROOK_BOB_BIN=/usr/local/bin/bob \
    ROOK_DB_PATH=/data/rook.db \
    ROOK_WORKSPACES=/data/workspaces \
    ROOK_ALLOWLIST=/opt/rook/config/allowlist.yaml \
    ROOK_DEMO_REPOS=/opt/rook/config/demos.yaml

USER rook
WORKDIR /home/rook
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4)"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["rook-start"]
