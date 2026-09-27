"""Request and response bodies of the server API (02 §11, CONTRACT). Requests forbid unknown fields."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatusName = Literal["queued", "running", "done", "failed", "cancelled"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Health(BaseModel):
    ok: bool
    version: str
    bob_mode: str
    proxied: bool  # the request came through the web proxy (its ROOK_PROXY_SECRET header matched)


class Me(BaseModel):
    id: str
    email: str
    github_connected: bool


class RepoOption(BaseModel):
    kind: Literal["github", "demo"]
    ref: str
    name: str
    private: bool
    language: str


class RepoChoice(_Request):
    kind: Literal["github", "demo"]
    ref: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class CreateOptions(_Request):
    auto: bool = False


class CreateRun(_Request):
    repo: RepoChoice
    request: str = Field(default="", max_length=2000)
    options: CreateOptions = Field(default_factory=CreateOptions)


class RunCreatedResponse(BaseModel):
    run_id: str


class RunRepo(BaseModel):
    kind: str
    ref: str
    name: str


class RunSummary(BaseModel):
    id: str
    repo: RunRepo
    status: RunStatusName
    created_at: str
    finished_at: str | None
    headline: str
    result: Literal["broken", "fixed"] | None
    coins: float
    last_seq: int


class RunDetail(BaseModel):
    run: RunSummary
    counterexamples: list[dict[str, Any]]


class AnswerBody(_Request):
    question_id: str = Field(min_length=1, max_length=100)
    answer: Any


class ChatBody(_Request):
    text: str = Field(min_length=1, max_length=2000)


class Ok(BaseModel):
    ok: bool
