"""Server settings (02 §11, 03 §6-§8), read from the environment by `ServerSettings.from_env()`.

Secrets are never read here except the guest-cookie signing key, which stays in memory and is never
returned by any route or written to a log.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from rook import __version__

_ORIGIN = re.compile(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA = re.compile(r"[0-9a-f]{40}")

_LOCAL = re.compile(r"http://(127\.0\.0\.1|localhost)(:\d{1,5})?$")
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")

DEFAULT_ORIGINS = ("http://localhost:3000",)


class DemoRepo(BaseModel):
    """One entry of the demo catalog shown by `GET /repos`; `ref@commit` must be on the sandbox allowlist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    commit: str
    name: str
    language: str = ""
    featured_rule: str | None = None  # the rule id the web pre-selects for guests (02 §5 approve_rules)

    @field_validator("ref")
    @classmethod
    def _ref(cls, v: str) -> str:
        if not _REPO.fullmatch(v):
            raise ValueError(f"demo ref must look like 'owner/name', not {v!r}")
        return v

    @field_validator("commit")
    @classmethod
    def _commit(cls, v: str) -> str:
        if not _SHA.fullmatch(v.lower()):
            raise ValueError("demo commit must be a full 40-character SHA")
        return v.lower()


def load_demo_repos(path: Path) -> list[DemoRepo]:
    """`{repos: [{ref, commit, name, language, featured_rule?}]}` (safe YAML)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [DemoRepo.model_validate(raw) for raw in data.get("repos") or []]


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = __version__
    bob_mode: Literal["live", "record", "replay"] = "live"
    db_path: Path = Path("~/.rook/server.db").expanduser()
    workspaces_root: Path = Path("~/.rook/workspaces").expanduser()
    web_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_ORIGINS))
    demo_repos: list[DemoRepo] = Field(default_factory=list)
    allowlist_path: Path | None = None  # the sandbox allowlist YAML (else the built-in DEFAULT_ALLOWLIST)
    guest_secret: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(32)))
    cookie_secure: bool = True
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Shared with the web proxy (Vercel middleware adds it as a header): only then is its X-Forwarded-For hop
    # trusted (03 §8). None = trust every hop.
    proxy_secret: SecretStr | None = None
    max_body_bytes: int = Field(default=64 * 1024, gt=0)
    rate_per_minute: int = Field(default=60, gt=0)
    runs_per_minute: int = Field(default=10, gt=0)
    guest_runs_per_day: int = Field(default=3, ge=0)  # per guest cookie
    guest_runs_per_ip_per_day: int = Field(default=10, ge=0)  # higher: people behind one NAT share an IP
    max_concurrent_runs: int = Field(default=3, gt=0)
    max_queued_runs: int = Field(default=6, ge=0)
    daily_coin_cap: float | None = Field(default=None, ge=0)
    # Supabase auth (03 §6). SUPABASE_URL alone turns on JWT verification (JWKS; plus HS256 with the secret);
    # the CLI sign-in also needs the public API key and this server's public URL (for the OAuth callback).
    supabase_url: str | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_anon_key: str | None = None  # public (the web has it too), sent as `apikey` to Supabase
    public_url: str | None = None  # e.g. https://203-0-113-7.sslip.io
    # The GitHub App (ROOK-031, 03 §6). App id + private key turn it on; the webhook needs its own secret. The
    # OAuth client (id + secret) is optional: with it, the setup callback proves the installation is the user's.
    github_app_id: int | None = Field(default=None, gt=0)
    github_app_slug: str = "rook-invariants"
    github_app_private_key: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    github_client_id: str | None = None  # public
    github_client_secret: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    github_web_url: str = "https://github.com"
    ping_seconds: float = Field(default=15.0, gt=0)
    flush_seconds: float = Field(default=0.25, gt=0)

    @field_validator("web_origins")
    @classmethod
    def _origins(cls, v: list[str]) -> list[str]:
        """Exact origins only: `*` would let any site call the API with the user's credentials."""
        for origin in v:
            if not _ORIGIN.fullmatch(origin):
                raise ValueError(f"web origin must be scheme://host[:port] (never '*'), not {origin!r}")
        return v

    @field_validator("supabase_url", "public_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        """An origin only (no path), https except for localhost; stored without a trailing slash."""
        if v is None:
            return None
        v = v.strip().rstrip("/")
        if not _ORIGIN.fullmatch(v) or not (v.startswith("https://") or _LOCAL.match(v)):
            raise ValueError(f"must be an https origin like https://example.com, not {v!r}")
        return v

    @field_validator("github_api_url", "github_web_url")
    @classmethod
    def _github_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not _ORIGIN.fullmatch(v) or not (v.startswith("https://") or _LOCAL.match(v)):
            raise ValueError(f"must be an https origin, not {v!r}")
        return v

    @field_validator("github_app_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG.fullmatch(v):
            raise ValueError(f"the GitHub App slug must be lowercase letters, digits and dashes, not {v!r}")
        return v

    @field_validator("guest_secret")
    @classmethod
    def _secret(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("the guest cookie secret must be at least 32 characters")
        return v

    @field_validator("proxy_secret")
    @classmethod
    def _proxy_secret(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) < 32:
            raise ValueError("the proxy secret must be at least 32 characters")
        return v

    def proxy_secret_value(self) -> str | None:
        return self.proxy_secret.get_secret_value() if self.proxy_secret is not None else None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ServerSettings:
        """ROOK_WEB_ORIGINS (comma list), ROOK_DB_PATH, ROOK_WORKSPACES, ROOK_BOB_MODE, ROOK_DEMO_REPOS (a YAML
        file), ROOK_ALLOWLIST, ROOK_GUEST_SECRET (else a random key per process), ROOK_PROXY_SECRET, ROOK_TRUSTED_PROXY_HOPS,
        ROOK_DAILY_COIN_CAP, SUPABASE_URL, SUPABASE_JWT_SECRET, SUPABASE_ANON_KEY, ROOK_PUBLIC_URL, GITHUB_APP_ID,
        GITHUB_APP_SLUG, GITHUB_APP_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET."""
        env = dict(os.environ) if env is None else env
        values: dict[str, object] = {}
        if origins := env.get("ROOK_WEB_ORIGINS"):
            values["web_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
        if db := env.get("ROOK_DB_PATH"):
            values["db_path"] = Path(db).expanduser()
        if root := env.get("ROOK_WORKSPACES"):
            values["workspaces_root"] = Path(root).expanduser()
        if mode := env.get("ROOK_BOB_MODE"):
            values["bob_mode"] = mode
        if demos := env.get("ROOK_DEMO_REPOS"):
            values["demo_repos"] = load_demo_repos(Path(demos))
        if allowlist := env.get("ROOK_ALLOWLIST"):
            values["allowlist_path"] = Path(allowlist).expanduser()
        if secret := env.get("ROOK_GUEST_SECRET"):
            values["guest_secret"] = SecretStr(secret)
        if proxy_secret := env.get("ROOK_PROXY_SECRET"):
            values["proxy_secret"] = SecretStr(proxy_secret)
        if hops := env.get("ROOK_TRUSTED_PROXY_HOPS"):
            values["trusted_proxy_hops"] = int(hops)
        if cap := env.get("ROOK_DAILY_COIN_CAP"):
            values["daily_coin_cap"] = float(cap)
        if supabase_url := env.get("SUPABASE_URL"):
            values["supabase_url"] = supabase_url
        if jwt_secret := env.get("SUPABASE_JWT_SECRET"):
            values["supabase_jwt_secret"] = SecretStr(jwt_secret)
        if anon_key := env.get("SUPABASE_ANON_KEY"):
            values["supabase_anon_key"] = anon_key.strip()
        if public_url := env.get("ROOK_PUBLIC_URL"):
            values["public_url"] = public_url
        if app_id := env.get("GITHUB_APP_ID", "").strip():
            values["github_app_id"] = int(app_id)
        if slug := env.get("GITHUB_APP_SLUG", "").strip():
            values["github_app_slug"] = slug
        if key := env.get("GITHUB_APP_PRIVATE_KEY", "").strip():
            values["github_app_private_key"] = SecretStr(key)
        if hook_secret := env.get("GITHUB_WEBHOOK_SECRET", "").strip():
            values["github_webhook_secret"] = SecretStr(hook_secret)
        if client_id := env.get("GITHUB_CLIENT_ID", "").strip():
            values["github_client_id"] = client_id
        if client_secret := env.get("GITHUB_CLIENT_SECRET", "").strip():
            values["github_client_secret"] = SecretStr(client_secret)
        return cls.model_validate(values)

    @property
    def github_app_configured(self) -> bool:
        return self.github_app_id is not None and self.github_app_private_key is not None

    def demo(self, ref: str) -> DemoRepo | None:
        return next((d for d in self.demo_repos if d.ref.lower() == ref.lower()), None)
