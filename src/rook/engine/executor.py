"""Async HTTP executor: runs rook.yaml actions against the sandboxed app (02 section 7, 03 section 5).

One `Executor` wraps one `httpx.AsyncClient`. Tests pass `httpx.ASGITransport(app=...)` to run
in-process; otherwise requests go over real HTTP to the sandbox `base_url`.

Egress guard: every request must go to the scheme, host and port of the base URL, or `EgressError`
is raised and nothing is sent. Redirects are never followed. Each request has a timeout and a
response size cap. Per-request failures are recorded in `StepResult.error`, never raised.
"""

import asyncio
import json
import random
import re
import secrets
import string
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx

from rook.model.jsonpath import extract
from rook.model.schema import (
    Action,
    Actor,
    Choice,
    HttpRequest,
    IntRange,
    ParallelStep,
    RookModel,
    SequenceStep,
    StateReader,
    Step,
    StringParam,
)
from rook.model.template import TemplateError, placeholders, render

EDGE_BIAS = 0.3
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 1_000_000

_DEFAULT_PORTS = {"http": 80, "https": 443}

PinnedRefs = Mapping[str, int]  # var -> index into ctx.pool[var]


class EgressError(RuntimeError):
    """A request would leave the sandbox (other scheme, host or port). Never sent; always raised.

    Raised from `run_step` only after every sibling sub-step has finished; `results` then holds all
    the step's results (the refused one with its `error` set), and their captures have been applied.
    """

    results: "list[StepResult] | None" = None


class ExecutorError(RuntimeError):
    """A per-request failure (transport error, timeout, size cap, setup failure...)."""


# --- per-sequence state ---


@dataclass
class SequenceContext:
    """State for one sequence: fresh values, the captured var pool and the set-up actors."""

    env: dict[str, Any] = field(default_factory=dict)
    fresh: dict[str, str] = field(init=False)
    pool: dict[str, list[Any]] = field(default_factory=dict)
    actors: dict[str, dict[str, Any]] = field(default_factory=dict)
    auth_headers: dict[str, dict[str, str]] = field(default_factory=dict)
    state_errors: list[str] = field(default_factory=list)
    _counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._token = secrets.token_hex(5)
        self.fresh = _fresh(self._token)

    def new_fresh(self) -> dict[str, str]:
        """New unique fresh values (one set per actor setup)."""
        self._counter += 1
        return _fresh(f"{self._token}x{self._counter}")


def _fresh(token: str) -> dict[str, str]:
    return {"id": token, "email": f"u{token}@rook.test"}


@dataclass(slots=True)
class StepResult:
    action: str
    actor: str
    params: dict[str, Any]
    refs_used: dict[str, Any]
    request: dict[str, Any]  # {"method", "path", "json"}
    status: int | None = None
    response_json: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0
    refs_index: dict[str, int] = field(default_factory=dict)  # var -> index into ctx.pool[var]

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and self.status < 400


@dataclass(slots=True)
class _Response:
    status: int | None = None
    json: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class _Prepared:
    action: Action
    actor: str
    params: dict[str, Any]
    refs: dict[str, Any]
    refs_index: dict[str, int]
    error: str | None = None


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _has_control_chars(text: str) -> bool:
    return _CONTROL_CHARS.search(text) is not None


# --- origin / egress ---


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    scheme = url.scheme.lower()
    return scheme, url.host.lower(), url.port or _DEFAULT_PORTS.get(scheme)


def _request_template(req: HttpRequest) -> dict[str, Any]:
    return req.model_dump(by_alias=True, exclude={"actor"}, exclude_none=True)


class Executor:
    """Async context manager wrapping one httpx client pointed at the sandbox base URL."""

    def __init__(
        self,
        model: RookModel,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        env: Mapping[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.model = model
        self.env: dict[str, Any] = dict(env or {})
        self.timeout = timeout
        self.max_bytes = max_bytes
        rendered = render(model.app.base_url, {"sandbox": {"base_url": base_url}})
        self.base_url = httpx.URL(str(rendered).rstrip("/"))
        if self.base_url.scheme not in _DEFAULT_PORTS or not self.base_url.host:
            raise ValueError(f"base_url must be an absolute http(s) URL, not {base_url!r}")
        self._origin = _origin(self.base_url)
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        # Pre-dumped request templates: rendering them is the hot path.
        self._actions = {a.name: a for a in model.actions}
        self._action_templates = {a.name: _request_template(a.request) for a in model.actions}
        self._actors: dict[str, Actor] = {a.name: a for a in model.actors}
        self._setup_templates = {
            a.name: [(_request_template(r), r.capture) for r in a.setup] for a in model.actors
        }
        self._readers = {r.name: r for r in model.state}
        self._reader_templates = {r.name: _request_template(r.request) for r in model.state}
        # Actors whose setup and auth use no `fresh` value (e.g. an admin login) set up the same way
        # every time, so their result is shared across sequences instead of logging in again.
        self._shareable_actors = {a.name for a in model.actors if _is_shareable(a)}
        self._actor_cache: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            transport=self._transport,
            base_url=self.base_url,
            follow_redirects=False,
            timeout=httpx.Timeout(self.timeout),
            trust_env=False,
        )
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def new_context(self) -> SequenceContext:
        return SequenceContext(env=dict(self.env))

    # --- low-level send ---

    def check_egress(self, url: httpx.URL) -> None:
        if _origin(url) != self._origin:
            raise EgressError(f"refused request to {url} (only {self.base_url} is allowed)")

    async def _send(self, req: Mapping[str, Any], headers: Mapping[str, str] | None = None) -> _Response:
        """Send one rendered request. Raises only EgressError; all other failures go into `error`."""
        if self._client is None:
            raise RuntimeError("Executor must be used as 'async with Executor(...)'")
        path = str(req["path"])
        if not path.startswith("/") or path.startswith("//"):
            raise EgressError(f"refused request path {path!r} (must be a single-'/' relative path)")
        all_headers = {str(k): str(v) for k, v in {**(req.get("headers") or {}), **(headers or {})}.items()}
        # Header or request-line injection must not depend on the transport rejecting it.
        bad = [f"path {path!r}"] if _has_control_chars(path) else []
        bad += [f"header {k!r}" for k, v in all_headers.items() if _has_control_chars(k + v)]
        if bad:
            return _Response(error=f"refused: control characters in {', '.join(bad)}")
        kwargs: dict[str, Any] = {"headers": all_headers or None, "params": req.get("query")}
        if "json" in req:
            kwargs["json"] = req["json"]

        start = time.perf_counter()
        result = _Response()
        try:
            if self._transport is not None:
                # An explicit transport (in-process app) is called directly: the client's cookie jar,
                # auth and redirect layers are not wanted here and cost more than a small app request.
                request = httpx.Request(req["method"], str(self.base_url) + path, **kwargs)
            else:
                request = self._client.build_request(req["method"], str(self.base_url) + path, **kwargs)
            self.check_egress(request.url)
            async with asyncio.timeout(self.timeout):
                if self._transport is not None:
                    response = await self._transport.handle_async_request(request)
                else:
                    response = await self._client.send(request, stream=True, follow_redirects=False)
                try:
                    result.status = response.status_code
                    body = await self._read_capped(response)
                finally:
                    await response.aclose()
            if body.strip():
                try:
                    result.json = json.loads(body)
                except ValueError:
                    result.error = f"response is not JSON (status {result.status})"
        except EgressError:
            raise
        except TimeoutError:
            result.error = f"timeout after {self.timeout:g}s"
        except ExecutorError as exc:
            result.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - transport errors and in-process app crashes are recorded
            result.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        result.elapsed_ms = (time.perf_counter() - start) * 1000
        return result

    async def _read_capped(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            raise ExecutorError(f"response too large ({declared} bytes > {self.max_bytes})")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.max_bytes:
                raise ExecutorError(f"response too large (> {self.max_bytes} bytes)")
            chunks.append(chunk)
        return b"".join(chunks)

    # --- actors ---

    async def setup_actor(self, ctx: SequenceContext, actor_name: str) -> dict[str, Any]:
        """Run the actor's setup requests with its own fresh values. Raises ExecutorError on failure."""
        actor = self._actors[actor_name]
        namespace: dict[str, Any] = {}
        render_ctx = {"fresh": ctx.new_fresh(), "env": ctx.env, "actor": namespace}
        for template, capture in self._setup_templates[actor_name]:
            try:
                req = render(template, render_ctx)
            except TemplateError as exc:
                raise ExecutorError(f"setup of actor {actor_name!r}: {exc}") from exc
            resp = await self._send(req)
            where = f"setup of actor {actor_name!r} ({req['method']} {req['path']})"
            if resp.error is not None:
                raise ExecutorError(f"{where}: {resp.error}")
            if resp.status is None or resp.status >= 400:
                raise ExecutorError(f"{where}: HTTP {resp.status}")
            for name, path in capture.items():
                value = extract(resp.json, path)
                if value is None:
                    raise ExecutorError(f"{where}: capture {name!r} ({path}) not found in response")
                namespace[name] = value
        headers: dict[str, str] = {}
        if actor.auth is not None:
            try:
                headers[actor.auth.header] = str(render(actor.auth.value, render_ctx))
            except TemplateError as exc:
                raise ExecutorError(f"auth of actor {actor_name!r}: {exc}") from exc
        ctx.actors[actor_name] = namespace
        ctx.auth_headers[actor_name] = headers
        return namespace

    async def _ensure_actor(self, ctx: SequenceContext, actor_name: str) -> None:
        if actor_name in ctx.actors:
            return
        cached = self._actor_cache.get(actor_name)
        if cached is not None:
            ctx.actors[actor_name], ctx.auth_headers[actor_name] = dict(cached[0]), dict(cached[1])
            return
        namespace = await self.setup_actor(ctx, actor_name)
        if actor_name in self._shareable_actors:
            self._actor_cache[actor_name] = (dict(namespace), dict(ctx.auth_headers[actor_name]))

    def clear_actor_cache(self) -> None:
        """Forget shared actor setups (e.g. after the sandbox restarts and old tokens are gone)."""
        self._actor_cache.clear()

    # --- params ---

    def choose_params(self, action: Action | str, rng: random.Random) -> dict[str, Any]:
        """Draw a value for every declared param of `action` (deterministic for a given rng state)."""
        if isinstance(action, str):
            action = self._actions[action]
        return draw_params(action, rng)

    # --- steps ---

    def _prepare(
        self, ctx: SequenceContext, step: Step, rng: random.Random, pinned: Mapping[str, int] | None
    ) -> _Prepared:
        action = self._actions[step.action]
        actor = step.actor or action.actor
        params = dict(step.params)
        for name, spec in action.params.items():
            if name not in params:
                params[name] = _draw(spec, rng)
        prepared = _Prepared(action, actor, params, {}, {})
        for var in action.requires:
            values = ctx.pool.get(var, [])
            if pinned is not None and var in pinned:
                index = pinned[var]
                if not 0 <= index < len(values):
                    prepared.error = f"pinned ref {var}[{index}] is out of range (pool has {len(values)})"
                    return prepared
            elif not values:
                prepared.error = f"no captured value for required var {var!r}"
                return prepared
            else:
                index = rng.randrange(len(values))
            prepared.refs_index[var] = index
            prepared.refs[var] = values[index]
        return prepared

    def _result(self, p: _Prepared) -> StepResult:
        return StepResult(
            p.action.name, p.actor, p.params, p.refs, {}, error=p.error, refs_index=p.refs_index
        )

    async def _execute(self, ctx: SequenceContext, p: _Prepared) -> StepResult:
        result = self._result(p)
        if p.error is not None:
            return result
        render_ctx = {
            "p": p.params,
            "ref": p.refs,
            "fresh": ctx.fresh,
            "env": ctx.env,
            "actor": ctx.actors.get(p.actor, {}),
        }
        try:
            req = render(self._action_templates[p.action.name], render_ctx)
        except TemplateError as exc:
            result.error = f"template error: {exc}"
            return result
        result.request = {"method": req["method"], "path": req["path"], "json": req.get("json")}
        resp = await self._send(req, ctx.auth_headers.get(p.actor))
        result.status, result.response_json = resp.status, resp.json
        result.error, result.elapsed_ms = resp.error, resp.elapsed_ms
        return result

    def _capture(self, ctx: SequenceContext, result: StepResult) -> None:
        if not result.ok:
            return
        for name, path in self._actions[result.action].capture.items():
            value = extract(result.response_json, path)
            if value is None:
                continue
            bucket = ctx.pool.setdefault(name, [])
            if isinstance(value, list):
                bucket.extend(v for v in value if v is not None)
            else:
                bucket.append(value)

    async def _setup_for(self, ctx: SequenceContext, prepared: list[_Prepared]) -> None:
        for p in prepared:
            if p.error is None and p.actor not in ctx.actors:
                try:
                    await self._ensure_actor(ctx, p.actor)
                except ExecutorError as exc:
                    p.error = str(exc)

    async def run_step(
        self,
        ctx: SequenceContext,
        step: SequenceStep,
        rng: random.Random,
        pinned_refs: PinnedRefs | Sequence[PinnedRefs | None] | None = None,
    ) -> StepResult | list[StepResult]:
        """Run one step (or a parallel step, which returns one result per sub-step, in order).

        Missing params are drawn with `rng`. Each `{{ref.x}}` picks a random pooled value with `rng`,
        unless `pinned_refs` gives its index into `ctx.pool[x]` (for a parallel step, pass one mapping
        per sub-step, or one mapping for all). The chosen indexes are in `StepResult.refs_index`.
        Captures are appended to `ctx.pool` (for a parallel step, in sub-step order after all finish).
        Raises EgressError only after all sub-steps finished and their captures were applied.
        """
        steps = step.parallel if isinstance(step, ParallelStep) else [step]
        if pinned_refs is None or isinstance(pinned_refs, Mapping):
            pins: list[PinnedRefs | None] = [pinned_refs] * len(steps)
        else:
            pins = list(pinned_refs)
            if len(pins) != len(steps):
                raise ValueError(f"pinned_refs has {len(pins)} entries for {len(steps)} sub-steps")
        # rng use is sequential and happens before any await: deterministic for a seed.
        prepared = [self._prepare(ctx, s, rng, pin) for s, pin in zip(steps, pins, strict=True)]
        await self._setup_for(ctx, prepared)
        outcomes = await asyncio.gather(*(self._execute(ctx, p) for p in prepared), return_exceptions=True)
        results: list[StepResult] = []
        failure: BaseException | None = None
        for p, outcome in zip(prepared, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                failure = failure or outcome
                result = self._result(p)
                result.error = f"{type(outcome).__name__}: {outcome}"
            else:
                result = outcome
                self._capture(ctx, result)
            results.append(result)
        if failure is not None:
            if isinstance(failure, EgressError):
                failure.results = results
            raise failure
        return results if isinstance(step, ParallelStep) else results[0]

    # --- state ---

    async def read_state(
        self, ctx: SequenceContext, reader_name: str | None = None, only_ids: Collection[Any] | None = None
    ) -> dict[str, dict[Any, dict[str, Any]]]:
        """Read entity state: `{reader: {id: {field: value}}}`.

        Reads every pooled value of each reader's `each` var, or only `only_ids` if given.
        Failed reads are left out and described in `ctx.state_errors`. EgressError is raised only
        after all of that reader's requests have finished.
        """
        readers = [self._readers[reader_name]] if reader_name else list(self._readers.values())
        out: dict[str, dict[Any, dict[str, Any]]] = {}
        for reader in readers:
            ids = list(dict.fromkeys(only_ids if only_ids is not None else ctx.pool.get(reader.each, [])))
            actor = reader.request.actor
            if actor is not None and ids:
                try:
                    await self._ensure_actor(ctx, actor)
                except ExecutorError as exc:
                    ctx.state_errors.append(f"state {reader.name!r}: {exc}")
                    out[reader.name] = {}
                    continue
            # Wait for every read, even if one is refused, so no request is left running.
            reads = await asyncio.gather(
                *(self._read_one(ctx, reader, v) for v in ids), return_exceptions=True
            )
            for read in reads:
                if isinstance(read, BaseException):
                    raise read
            out[reader.name] = {v: fields for v, fields in zip(ids, reads, strict=True) if fields is not None}
        return out

    async def _read_one(self, ctx: SequenceContext, reader: StateReader, value: Any) -> dict[str, Any] | None:
        where = f"state {reader.name!r} {reader.each}={value!r}"
        try:
            req = render(self._reader_templates[reader.name], {reader.each: value, "env": ctx.env})
        except TemplateError as exc:
            ctx.state_errors.append(f"{where}: {exc}")
            return None
        headers = ctx.auth_headers.get(reader.request.actor) if reader.request.actor else None
        resp = await self._send(req, headers)
        if resp.error is not None or resp.status is None or resp.status >= 400:
            ctx.state_errors.append(f"{where}: {resp.error or f'HTTP {resp.status}'}")
            return None
        return {name: extract(resp.json, path) for name, path in reader.fields.items()}


def _is_shareable(actor: Actor) -> bool:
    names = placeholders([r.model_dump(by_alias=True) for r in actor.setup])
    if actor.auth is not None:
        names |= placeholders(actor.auth.value)
    return not any(name.split(".", 1)[0] == "fresh" for name in names)


# --- param drawing ---


def draw_params(action: Action, rng: random.Random) -> dict[str, Any]:
    """Draw a value for every declared param of `action` (deterministic for a given rng state).

    Int params pick one of their edge values with probability EDGE_BIAS, else a uniform value.
    """
    return {name: _draw(spec, rng) for name, spec in action.params.items()}


def _draw(spec: IntRange | Choice | StringParam, rng: random.Random) -> Any:
    if isinstance(spec, IntRange):
        lo, hi = spec.int_range
        edges = spec.edges or [lo, hi]
        if rng.random() < EDGE_BIAS:
            return rng.choice(edges)
        return rng.randint(lo, hi)
    if isinstance(spec, Choice):
        return rng.choice(spec.choice)
    s = spec.string
    if s.values is not None:
        return rng.choice(s.values)
    assert s.pattern is not None
    return _from_pattern(s.pattern, rng)


_CLASSES = {
    "d": string.digits,
    "w": string.ascii_letters + string.digits + "_",
    "s": " ",
}
_ANY = string.ascii_letters + string.digits
_UNSUPPORTED = set("()|")


def _from_pattern(pattern: str, rng: random.Random) -> str:
    """Generate a string for simple regexes (literals, [a-z0-9] classes, \\d \\w, . and quantifiers).

    Anything else (groups, alternation, ...) or a generated value that does not match falls back to
    `s<number>`.
    """
    fallback = f"s{rng.randint(0, 9999)}"
    try:
        value = _generate(pattern.removeprefix("^").removesuffix("$"), rng)
    except ValueError:
        return fallback
    return value if re.fullmatch(pattern, value) else fallback


def _generate(pat: str, rng: random.Random) -> str:
    out: list[str] = []
    i = 0
    while i < len(pat):
        c = pat[i]
        if c in _UNSUPPORTED:
            raise ValueError(pat)
        if c == "\\":
            if i + 1 >= len(pat):
                raise ValueError(pat)
            nxt = pat[i + 1]
            chars = _CLASSES.get(nxt, nxt if not nxt.isalnum() else None)
            if chars is None:
                raise ValueError(pat)
            i += 2
        elif c == "[":
            end = pat.find("]", i + 1)
            if end < 0:
                raise ValueError(pat)
            chars = _char_class(pat[i + 1 : end])
            i = end + 1
        elif c == ".":
            chars, i = _ANY, i + 1
        elif c in "*+?{":
            raise ValueError(pat)
        else:
            chars, i = c, i + 1
        lo, hi, i = _quantifier(pat, i)
        out.extend(rng.choice(chars) for _ in range(rng.randint(lo, hi)))
    return "".join(out)


def _char_class(body: str) -> str:
    if not body or body.startswith("^"):
        raise ValueError(body)
    chars: list[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            chars.append(_CLASSES.get(body[i + 1], body[i + 1]))
            i += 2
        elif i + 2 < len(body) and body[i + 1] == "-":
            lo, hi = ord(body[i]), ord(body[i + 2])
            if lo > hi:
                raise ValueError(body)
            chars.append("".join(map(chr, range(lo, hi + 1))))
            i += 3
        else:
            chars.append(body[i])
            i += 1
    return "".join(chars)


_REPEAT = re.compile(r"\{(\d{1,3})(?:,(\d{1,3})?)?\}")


def _quantifier(pat: str, i: int) -> tuple[int, int, int]:
    if i >= len(pat):
        return 1, 1, i
    c = pat[i]
    if c == "?":
        return 0, 1, i + 1
    if c == "*":
        return 0, 8, i + 1
    if c == "+":
        return 1, 8, i + 1
    if c == "{":
        m = _REPEAT.match(pat, i)
        if m is None:
            raise ValueError(pat)
        lo = int(m.group(1))
        if m.group(2) is not None:
            hi = int(m.group(2))
        elif pat[m.end() - 2] == ",":
            hi = lo + 8
        else:
            hi = lo
        if lo > hi:
            raise ValueError(pat)
        return lo, hi, m.end()
    return 1, 1, i
