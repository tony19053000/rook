"""The Replayer (02_ARCHITECTURE.md section 7.5): re-runs one counterexample N times and reports `k/N`.

Each replay runs the exact recorded sequence (concrete params, pinned refs) from a fresh
`SequenceContext`, so every replay creates its own actors and entities. The Judge alone decides
whether a replay reproduced the counterexample: it counts when the first rule the Judge finds broken
is the counterexample's rule_id (entity and step index are not compared, since ids change on every
run). Replays run one after another, not concurrently, so they don't interfere with each other.

`flaky` means 0 < k < N (expected for races); k == 0 means the rule held every time (which is what
the Verifier wants on a fixed app).
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from rook.core.events import EngineFinished, EngineProgress, EngineStarted, EventBus
from rook.engine.executor import Executor
from rook.engine.judge import Judge, Violation
from rook.engine.runner import PROGRESS_INTERVAL, TraceStep
from rook.engine.shrinker import replay_trace
from rook.model.schema import RookModel

DEFAULT_REPLAYS = 10


@dataclass
class ReplayResult:
    rule_id: str
    n: int
    violations: list[Violation | None]  # per replay: the Judge's violation of `rule_id`, or None

    @property
    def k(self) -> int:
        return sum(v is not None for v in self.violations)

    @property
    def flaky(self) -> bool:
        return 0 < self.k < self.n

    @property
    def reproduced(self) -> str:
        """`k/N`, as in the `counterexample.saved` event."""
        return f"{self.k}/{self.n}"


class Replayer:
    """Replays a trace N times. `executor` is an entered Executor or a factory for one."""

    def __init__(
        self,
        model: RookModel,
        executor: Executor | Callable[[], Executor],
        bus: EventBus | None,
        run_id: str,
        *,
        n: int = DEFAULT_REPLAYS,
        seed: int | str = 0,
        judge: Judge | None = None,
    ) -> None:
        if n < 1:
            raise ValueError("n must be at least 1")
        self.model = model
        self._executor_source = executor
        self.bus = bus
        self.run_id = run_id
        self.n = n
        self.seed = seed
        self.judge = judge or Judge(model)

    async def replay(self, violation: Violation | str, trace: Sequence[TraceStep]) -> ReplayResult:
        """Replay `trace` N times; a replay counts if the Judge finds `violation`'s rule broken first."""
        rule_id = violation if isinstance(violation, str) else violation.rule_id
        label = f"{len(trace)} steps x {self.n}, rule {rule_id}"
        await self._publish("engine.started", EngineStarted(worker="replayer", label=label))
        try:
            if isinstance(self._executor_source, Executor):
                result = await self._replay(self._executor_source, rule_id, trace)
            else:
                async with self._executor_source() as ex:
                    result = await self._replay(ex, rule_id, trace)
        except BaseException as exc:
            summary = f"replay stopped: {type(exc).__name__}: {exc}"
            await self._publish(
                "engine.finished", EngineFinished(worker="replayer", ok=False, summary=summary)
            )
            raise
        summary = f"reproduced {result.reproduced}" + (" (flaky)" if result.flaky else "")
        await self._publish(
            "engine.finished", EngineFinished(worker="replayer", ok=result.k > 0, summary=summary)
        )
        return result

    async def _replay(self, ex: Executor, rule_id: str, trace: Sequence[TraceStep]) -> ReplayResult:
        result = ReplayResult(rule_id, self.n, [])
        last_emit = float("-inf")
        for i in range(self.n):
            violation, _ = await replay_trace(ex, self.judge, trace, seed=f"{self.seed}:{i}")
            same = violation is not None and violation.rule_id == rule_id
            result.violations.append(violation if same else None)
            now = time.monotonic()
            if i + 1 == self.n or now - last_emit >= PROGRESS_INTERVAL:
                last_emit = now
                progress = EngineProgress(
                    worker="replayer",
                    pct=round(100 * (i + 1) / self.n, 1),
                    label=f"{result.k}/{i + 1} reproduced",
                    count=i + 1,
                )
                await self._publish("engine.progress", progress)
        return result

    async def _publish(self, event_type: str, data: Any) -> None:
        if self.bus is not None:
            await self.bus.publish(self.run_id, event_type, data)
