"""Smoke-test a deployed Rook server like a guest in the browser would: health, demo catalog, one demo run.

    uv run python deploy/smoke.py https://203-0-113-7.sslip.io        # the EC2 server (through Caddy)
    uv run python deploy/smoke.py http://localhost:18080              # the local compose stack

It starts a run on the demo repo, streams its events (SSE), answers each question the way a demo user would
(approve the refund rule, apply the fix, pick "report" when an agent fails) and waits for `run.finished`.
`--approve all` approves every proposed rule instead, as the web UI does; `--approve both` runs both.
Exit code 0 when the run has a diagnosis the Diagnosis Reviewer approved and, in replay mode, spent 0 Bobcoins
and: approving the refund rule, ended `done` with the fix verified (verify.done verified=true, fix.committed, a
"verified" summary; replay runs the replayed patch from the run's workspace, docs/02 §8); approving every rule,
ended `done` with the fix honestly NOT verified: VERIFY's fresh search breaks another approved rule, since
minishop has four planted bugs, so the patch is reverted, not committed, and the summary says so (docs/04 §3.8). In live mode the server cannot verify a fix (it skips
VERIFY): the run must end `done` and the fix is printed, not required.
The `rook_guest` cookie is kept by hand: it is `Secure`, and a local test runs over plain HTTP.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from typing import Any

import httpx


class Guest:
    def __init__(self, base: str, timeout: float) -> None:
        self.base = base.rstrip("/") + "/api/v1"
        self.http = httpx.Client(timeout=httpx.Timeout(timeout, read=60.0), follow_redirects=False)
        self.cookie = ""

    def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        res = self.http.request(method, self.base + path, headers=self._headers(kwargs), **kwargs)
        self._keep(res)
        return res

    def _headers(self, kwargs: dict[str, Any]) -> dict[str, str]:
        headers = dict(kwargs.pop("headers", None) or {})
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers

    def _keep(self, res: httpx.Response) -> None:
        for raw in res.headers.get_list("set-cookie"):
            if raw.startswith("rook_guest="):
                self.cookie = raw.split(";", 1)[0]

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        res = self.call(method, path, **kwargs)
        if res.status_code >= 400:
            raise SystemExit(f"FAIL {method} {path}: HTTP {res.status_code} {res.text[:300]}")
        return res.json()


def answer_for(question: dict[str, Any], approve: str = "refund") -> Any:
    """`approve`: "refund" approves the refund rule only (like the CLI demo), "all" every proposed rule (what
    the web UI's approve button sends)."""
    kind = question.get("kind")
    options = question.get("options") or []
    if kind == "approve_rules":
        if approve == "all":
            return "all"
        rules = (question.get("payload") or {}).get("rules") or []
        refund = [r["id"] for r in rules if r.get("accepted") and "refund" in r.get("check", "")
                  and "paid" in r.get("check", "")]
        return refund or "all"
    if kind in ("fix", "pr"):
        return "yes"
    if kind == "menu":
        ids = [o.get("id") for o in options]
        return "report" if "report" in ids else (ids[0] if ids else "yes")
    return options[0].get("id") if options else "yes"


def stream(guest: Guest, run_id: str, deadline: float, approve: str = "refund"
           ) -> tuple[dict[str, Any], Counter[str], dict[str, dict[str, Any]]]:
    types: Counter[str] = Counter()
    seen: dict[str, dict[str, Any]] = {}  # a reviewed diagnosis.ready; the last verify.done, fix.committed
    with guest.http.stream("GET", f"{guest.base}/runs/{run_id}/events",
                           headers={"accept": "text/event-stream", "cookie": guest.cookie}) as res:
        if res.status_code != 200 or not res.headers.get("content-type", "").startswith("text/event-stream"):
            raise SystemExit(f"FAIL events: HTTP {res.status_code} {res.headers.get('content-type')}")
        data: list[str] = []
        for line in res.iter_lines():
            if time.monotonic() > deadline:
                raise SystemExit("FAIL timed out waiting for run.finished")
            if line.startswith("data:"):
                data.append(line[5:].strip())
                continue
            if line or not data:
                continue
            event = json.loads("\n".join(data))
            data = []
            types[event["type"]] += 1
            body = event.get("data") or {}
            if event["type"] in ("verify.done", "fix.committed"):
                seen[event["type"]] = body
            # Keep a reviewed diagnosis: a later re-DIAGNOSE (after a failed VERIFY) may end without one.
            if event["type"] == "diagnosis.ready" and ("diagnosis.ready" not in seen or body.get("reviewed")):
                seen["diagnosis.ready"] = body
            if event["type"] == "verify.step" and body.get("check") == "fresh_search" \
                    and body.get("status") != "running":
                seen["fresh_search"] = body
            if event["type"] == "run.phase":
                print(f"  phase {body.get('phase')}")
            elif event["type"] == "agent.finished" and not body.get("ok"):
                print(f"  agent {body.get('agent')} failed: {body.get('summary')}")
            elif event["type"] == "question.asked":
                answer = answer_for(body, approve)
                print(f"  question {body.get('kind')} -> {json.dumps(answer)}")
                reply = guest.json("POST", f"/runs/{run_id}/answers",
                                   json={"question_id": body.get("question_id"), "answer": answer})
                if reply.get("ok") is not True:
                    raise SystemExit(f"FAIL the {body.get('kind')} answer was refused")
            elif event["type"] == "run.finished":
                return body, types, seen
    raise SystemExit("FAIL the event stream ended without run.finished")


def demo_run(guest: Guest, args: argparse.Namespace, approve: str, deadline: float, bob_mode: Any) -> bool:
    """One guest run on the demo repo; True when it ended as expected for `approve` (module docstring)."""
    print(f"--- demo run approving {'every proposed rule' if approve == 'all' else 'the refund rule'} ---")
    created = guest.json("POST", "/runs", json={"repo": {"kind": "demo", "ref": args.repo},
                                                "request": args.request, "options": {"auto": False}})
    run_id = created["run_id"]
    print(f"run {run_id} started")
    finished, types, seen = stream(guest, run_id, deadline, approve)
    detail = guest.json("GET", f"/runs/{run_id}")
    coins = detail["run"]["coins"]
    print(f"run.finished: status={finished.get('status')} summary={finished.get('summary')!r}")
    print(f"events: {dict(types)}")
    print(f"counterexamples: {len(detail['counterexamples'])}, coins: {coins}")
    diagnosis = seen.get("diagnosis.ready") or {}
    verify = seen.get("verify.done")
    print(f"diagnosis: {diagnosis.get('file')}:{diagnosis.get('line')} reviewed={diagnosis.get('reviewed')}")
    print(f"fix: {'verified=' + str(verify.get('verified')) if verify else 'not verified (no verify.done)'}")
    replay_all = bob_mode == "replay" and approve == "all"
    if finished.get("status") != "done":
        print("FAIL the run did not end `done`")
        return False
    if not (diagnosis.get("reviewed") is True and diagnosis.get("file")):
        print("FAIL no diagnosis approved by the Diagnosis Reviewer (DIAGNOSE did not replay)")
        return False
    if bob_mode == "replay" and coins != 0:
        print("FAIL a replay run spent Bobcoins")
        return False
    if replay_all:
        if not honestly_unverified(finished, seen):
            print("FAIL expected the fix NOT verified (fresh search broke another approved rule), not committed")
            return False
    elif bob_mode == "replay" and not fix_verified(finished, seen):
        print("FAIL the replayed fix was not verified and committed")
        return False
    return True


def honestly_unverified(finished: dict[str, Any], seen: dict[str, dict[str, Any]]) -> bool:
    """Approving every rule: VERIFY ran and found the fix NOT verified because the fresh search broke another
    approved rule, nothing was committed, and the summary names that rule (no paths or recording keys)."""
    verify = seen.get("verify.done") or {}
    fresh = seen.get("fresh_search") or {}
    summary = str(finished.get("summary") or "")
    broken = re.search(r"new violation of rule (\S+)", str(fresh.get("detail") or ""))
    return (verify.get("verified") is False and fresh.get("status") == "failed" and "fix.committed" not in seen
            and broken is not None and f"another approved rule still broken: {broken.group(1)}." in summary
            and "NOT verified: the patch was reverted and not shipped" in summary
            and not re.search(r"/tmp/|/home/|recording|[0-9a-f]{64}", summary))


def fix_verified(finished: dict[str, Any], seen: dict[str, dict[str, Any]]) -> bool:
    """The run verified its fix: verify.done verified=true, the fix committed, and the summary says so."""
    verify = seen.get("verify.done") or {}
    committed = seen.get("fix.committed") or {}
    summary = str(finished.get("summary") or "").lower()
    return (verify.get("verified") is True and bool(committed) and committed.get("cx_id") == verify.get("cx_id")
            and "verified" in summary and "not verified" not in summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", help="the server origin, e.g. https://203-0-113-7.sslip.io")
    parser.add_argument("--repo", default="rook-demo/minishop", help="the demo repo ref")
    parser.add_argument("--request", default="find and fix a bug")
    parser.add_argument("--approve", choices=("refund", "all", "both"), default="refund",
                        help="approve the refund rule only (the CLI demo), every rule (the web UI) or run both")
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds for the whole smoke test")
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.timeout
    guest = Guest(args.base, timeout=30.0)

    health = guest.json("GET", "/health")
    print(f"health: {health}")
    repos = guest.json("GET", "/repos")
    if not any(r.get("kind") == "demo" and r.get("ref") == args.repo for r in repos):
        raise SystemExit(f"FAIL {args.repo} is not in the demo catalog: {[r.get('ref') for r in repos]}")
    print(f"repos: {[r['ref'] for r in repos]}")
    modes = ["refund", "all"] if args.approve == "both" else [args.approve]
    results = [demo_run(guest, args, approve, deadline, health.get("bob_mode")) for approve in modes]  # run all
    if not all(results):
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
