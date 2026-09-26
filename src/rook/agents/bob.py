"""BobClient: runs `bob run` as a subprocess and turns its NDJSON stream into events (02_ARCHITECTURE.md §5.1).

Security (03_SECURITY_ACCESS.md §2, §4): the API key goes only into the child env (never argv) and is
registered for redaction; stdin is always DEVNULL (bob hangs otherwise); `--disable-mcp` is always passed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from rook.agents.recorder import Recorder, RecordingWriter, recording_key, replay_lines
from rook.core.events import (
    AgentFinished,
    AgentProgress,
    AgentStarted,
    CostUpdate,
    EventBus,
    redact_text,
    register_secret,
)

BobMode = Literal["live", "record", "replay"]

NODE24_BIN = Path.home() / ".nvm" / "versions" / "node" / "v24.21.0" / "bin"
DEFAULT_BOB_BIN = NODE24_BIN / "bob"
MAX_ATTEMPTS = 3
# The only host env vars the Bob child inherits (plus explicit `env=` keys). Bob can be prompt-injected,
# so it must never see host secrets such as SUPABASE_JWT_SECRET or GITHUB_APP_PRIVATE_KEY.
CHILD_ENV_ALLOWLIST = (
    "PATH", "HOME", "BOB_API_KEY", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "TMP", "TEMP",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
)
_STREAM_LIMIT = 16 * 1024 * 1024  # tool_result lines can hold whole files
_SUMMARY_MAX = 120
_DETAIL_MAX = 160


class BobError(RuntimeError):
    """bob exited without a successful result (bad status, crash or timeout)."""


class BobTimeout(BobError):
    pass


class AgentOutputError(BobError):
    """The agent's output failed validation on every attempt."""


@dataclass
class AgentResult:
    output: BaseModel
    text: str
    cost: float  # coins reported by bob over all attempts (the original cost when replayed)
    recorded: bool
    call_id: str


@dataclass
class _Stream:
    chunks: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        return "".join(self.chunks)


def resolve_bin(explicit: str | os.PathLike[str] | None = None) -> str:
    if explicit:
        return str(explicit)
    if env_bin := os.environ.get("ROOK_BOB_BIN"):
        return env_bin
    if DEFAULT_BOB_BIN.exists():
        return str(DEFAULT_BOB_BIN)
    return shutil.which("bob") or "bob"


def build_argv(
    bin_path: str, slug: str, prompt: str, workspace: str, max_turns: int, max_cost: float | None
) -> list[str]:
    argv = [bin_path, "run", "--mode", slug, "--format", "stream-json", "--workspace", workspace,
            "--max-turns", str(max_turns), "--disable-mcp", "--trust", "--accept-license"]
    if max_cost is not None:
        argv += ["--max-cost", str(max_cost)]
    return [*argv, prompt]


_FENCE_RE = re.compile(r"```[ \t]*(json)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Return the last fenced ```json block, else the last bare top-level JSON object. Raises ValueError."""
    fenced = [m for m in _FENCE_RE.finditer(text) if m.group(1) or m.group(2).lstrip().startswith(("{", "["))]
    if fenced:
        return json.loads(fenced[-1].group(2))
    decoder = json.JSONDecoder()
    last: Any = None
    found = False
    pos = text.find("{")
    while pos != -1:
        try:
            obj, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("{", pos + 1)
            continue
        last, found = obj, True
        pos = text.find("{", end)
    if not found:
        raise ValueError("no JSON block found in the reply")
    return last


def tool_detail(tool_name: str, params: dict[str, Any], workspace: str) -> str:
    def rel(value: Any) -> str:
        p = str(value or ".")
        with contextlib.suppress(ValueError):
            if Path(p).is_absolute():
                r = os.path.relpath(p, workspace)
                if not r.startswith(".."):
                    return r
        return p

    path = params.get("path") or params.get("file_path")
    if tool_name == "read_file":
        detail = f"reading {rel(path)}"
    elif tool_name == "list_files":
        detail = f"listing {rel(path)}"
    elif tool_name == "search_files":
        needle = params.get("regex") or params.get("pattern") or params.get("query") or ""
        detail = f"searching for {needle}" + (f" in {rel(path)}" if path else "")
    elif tool_name in ("write_to_file", "apply_diff"):
        detail = f"editing {rel(path)}"
    else:
        detail = f"using {tool_name}"
    return detail[:_DETAIL_MAX]


def _summarize(text: str, model: type[BaseModel]) -> str:
    before_json = text.split("```", 1)[0]
    for line in before_json.splitlines():
        line = line.strip()
        if line and not line.startswith("{"):
            return line[:_SUMMARY_MAX]
    return f"returned {model.__name__}"[:_SUMMARY_MAX]


def _retry_prompt(prompt: str, error: str) -> str:
    return (
        f"{prompt}\n\nYour previous reply was rejected because its final JSON block was invalid:\n{error}\n"
        "Reply again and end with exactly one fenced ```json block that matches the required schema."
    )


class BobClient:
    def __init__(
        self,
        bus: EventBus,
        run_id: str,
        *,
        bin: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        mode: BobMode | None = None,
        recordings_dir: Path | str | None = None,
        timeout: float = 300,
        replay_speed: float = 3.0,
        replay_max_gap: float = 1.5,
    ) -> None:
        self.bus = bus
        self.run_id = run_id
        self.bin = resolve_bin(bin)
        # `env` is added to the child env *without* the allowlist filter. Only pass the few
        # values bob needs (e.g. BOB_API_KEY); never pass os.environ here.
        self.env = dict(env) if env is not None else {}
        resolved_mode = mode or os.environ.get("ROOK_BOB_MODE", "live")
        if resolved_mode not in ("live", "record", "replay"):
            raise ValueError(f"invalid ROOK_BOB_MODE: {resolved_mode!r}")
        self.mode: BobMode = resolved_mode  # type: ignore[assignment]
        self.record = self.mode == "record" or (self.mode == "live" and os.environ.get("ROOK_BOB_RECORD") == "1")
        self.recorder = Recorder(recordings_dir)
        self.timeout = timeout
        self.replay_speed = replay_speed
        self.replay_max_gap = replay_max_gap
        self.total_cost = 0.0  # coins charged against the budget (replays are free)
        register_secret(self.env.get("BOB_API_KEY") or os.environ.get("BOB_API_KEY"))

    async def call(
        self,
        agent_id: str,
        slug: str,
        prompt: str,
        workspace: str | os.PathLike[str],
        output_model: type[BaseModel],
        max_turns: int = 8,
        max_cost: float | None = None,
    ) -> AgentResult:
        ws = str(Path(workspace).resolve())
        call_id = f"c_{uuid.uuid4().hex[:10]}"
        await self._publish("agent.started", AgentStarted(agent=agent_id, call_id=call_id, detail="starting"))
        cost = 0.0
        recorded = self.mode == "replay"
        attempt_prompt = prompt
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                stream = await self._attempt(agent_id, call_id, slug, attempt_prompt, ws, max_turns, max_cost)
                assert stream.result is not None
                attempt_cost = float((stream.result.get("stats") or {}).get("session_costs") or 0.0)
                cost += attempt_cost
                if not recorded:
                    self.total_cost += attempt_cost
                await self._publish("cost.update", CostUpdate(coins_total=round(self.total_cost, 6)))
                status = stream.result.get("status")
                if status != "success":
                    raise BobError(f"bob returned status {status!r}")
                text = stream.text
                try:
                    output = output_model.model_validate(extract_json(text))
                except (ValueError, ValidationError) as exc:
                    if attempt == MAX_ATTEMPTS:
                        raise AgentOutputError(
                            f"{agent_id}: invalid output after {MAX_ATTEMPTS} attempts: {exc}"
                        ) from exc
                    await self._publish("agent.progress", AgentProgress(
                        agent=agent_id, call_id=call_id, detail="output did not match the schema; retrying"))
                    attempt_prompt = _retry_prompt(prompt, str(exc))
                    continue
                await self._finish(agent_id, call_id, True, _summarize(text, output_model), cost, recorded)
                return AgentResult(output=output, text=text, cost=cost, recorded=recorded, call_id=call_id)
        except Exception as exc:
            await self._finish(agent_id, call_id, False, str(exc).splitlines()[0] if str(exc) else
                               type(exc).__name__, cost, recorded)
            raise
        raise AssertionError("unreachable")

    async def _attempt(
        self, agent_id: str, call_id: str, slug: str, prompt: str, ws: str, max_turns: int,
        max_cost: float | None,
    ) -> _Stream:
        stream = _Stream()

        async def on_line(raw: str) -> None:
            await self._handle_line(raw, stream, agent_id, call_id, ws)

        key = recording_key(slug, prompt)
        failure = ""
        if self.mode == "replay":
            entries = self.recorder.load(key)
            async for raw in replay_lines(entries, speed=self.replay_speed, max_gap=self.replay_max_gap):
                await on_line(raw)
        else:
            writer = RecordingWriter() if self.record else None
            argv = build_argv(self.bin, slug, prompt, ws, max_turns, max_cost)
            returncode, stderr_tail = await self._run_live(argv, ws, on_line, writer)
            if writer is not None and stream.result is not None:
                self.recorder.save(key, writer.entries)
            failure = f" (exit code {returncode}){': ' + stderr_tail if stderr_tail else ''}"
        if stream.result is None:
            raise BobError(redact_text(f"bob stream ended without a result line{failure}"))
        return stream

    def _child_env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in CHILD_ENV_ALLOWLIST if k in os.environ}
        env.update(self.env)
        extra = [str(NODE24_BIN)]
        bin_dir = str(Path(self.bin).parent)
        if bin_dir not in ("", "."):
            extra.insert(0, bin_dir)
        env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
        return env

    async def _run_live(
        self, argv: list[str], ws: str, on_line: Callable[[str], Awaitable[None]],
        writer: RecordingWriter | None,
    ) -> tuple[int | None, str]:
        """Run bob, feeding each stdout line to `on_line`. Returns (exit code, redacted stderr tail)."""
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,  # MANDATORY: bob hangs forever on an open stdin
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._child_env(),
            cwd=ws,  # `--trust` trusts the cwd; workspace custom modes load only from a trusted folder
            start_new_session=True,  # own process group, so a timeout kills node's children too
            limit=_STREAM_LIMIT,
        )
        assert proc.stdout is not None and proc.stderr is not None
        stderr_task = asyncio.create_task(proc.stderr.read())

        async def pump() -> None:
            assert proc.stdout is not None
            while line := await proc.stdout.readline():
                raw = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not raw.strip():
                    continue
                if writer is not None:
                    writer.add(raw)
                await on_line(raw)
            await proc.wait()

        try:
            async with asyncio.timeout(self.timeout):
                await pump()
        except TimeoutError as exc:
            raise BobTimeout(f"bob timed out after {self.timeout:g}s") from exc
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
            stderr = (await stderr_task).decode("utf-8", errors="replace")
        return proc.returncode, redact_text(" ".join(stderr[-300:].split()))

    async def _handle_line(self, raw: str, stream: _Stream, agent_id: str, call_id: str, ws: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return  # bob sometimes prints non-JSON notices; they carry no data
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "message" and msg.get("role") == "assistant":
            stream.chunks.append(str(msg.get("content") or ""))
        elif kind == "tool_use":
            params = msg.get("parameters") if isinstance(msg.get("parameters"), dict) else {}
            detail = tool_detail(str(msg.get("tool_name") or "tool"), params, ws)
            await self._publish("agent.progress", AgentProgress(agent=agent_id, call_id=call_id, detail=detail))
        elif kind == "result":
            stream.result = msg

    async def _finish(
        self, agent_id: str, call_id: str, ok: bool, summary: str, cost: float, recorded: bool
    ) -> None:
        await self._publish("agent.finished", AgentFinished(
            agent=agent_id, call_id=call_id, ok=ok, summary=summary[:_SUMMARY_MAX], cost=round(cost, 6),
            recorded=recorded))

    async def _publish(self, event_type: str, data: BaseModel) -> None:
        await self.bus.publish(self.run_id, event_type, data)
