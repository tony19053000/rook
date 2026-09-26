"""Smoke-test a deployed Rook server like a guest in the browser would: health, demo catalog, one demo run.

    uv run python deploy/smoke.py https://203-0-113-7.sslip.io        # the EC2 server (through Caddy)
    uv run python deploy/smoke.py http://localhost:18080              # the local compose stack

It starts a run on the demo repo, streams its events (SSE), answers each question the way a demo user would
(approve the refund rule, apply the fix, pick "report" when an agent fails) and waits for `run.finished`.
Exit code 0 when the run reached a terminal status and, in replay mode, spent 0 Bobcoins.
The `rook_guest` cookie is kept by hand: it is `Secure`, and a local test runs over plain HTTP.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from typing import Any

import httpx

TERMINAL = {"done", "failed", "cancelled"}


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


def answer_for(question: dict[str, Any]) -> Any:
    kind = question.get("kind")
    options = question.get("options") or []
    if kind == "approve_rules":
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


def stream(guest: Guest, run_id: str, deadline: float) -> tuple[dict[str, Any], Counter[str]]:
    types: Counter[str] = Counter()
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
            if event["type"] == "run.phase":
                print(f"  phase {body.get('phase')}")
            elif event["type"] == "agent.finished" and not body.get("ok"):
                print(f"  agent {body.get('agent')} failed: {body.get('summary')}")
            elif event["type"] == "question.asked":
                answer = answer_for(body)
                print(f"  question {body.get('kind')} -> {json.dumps(answer)}")
                reply = guest.json("POST", f"/runs/{run_id}/answers",
                                   json={"question_id": body.get("question_id"), "answer": answer})
                if reply.get("ok") is not True:
                    raise SystemExit(f"FAIL the {body.get('kind')} answer was refused")
            elif event["type"] == "run.finished":
                return body, types
    raise SystemExit("FAIL the event stream ended without run.finished")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", help="the server origin, e.g. https://203-0-113-7.sslip.io")
    parser.add_argument("--repo", default="rook-demo/minishop", help="the demo repo ref")
    parser.add_argument("--request", default="find and fix a bug")
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds for the whole run")
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.timeout
    guest = Guest(args.base, timeout=30.0)

    health = guest.json("GET", "/health")
    print(f"health: {health}")
    repos = guest.json("GET", "/repos")
    if not any(r.get("kind") == "demo" and r.get("ref") == args.repo for r in repos):
        raise SystemExit(f"FAIL {args.repo} is not in the demo catalog: {[r.get('ref') for r in repos]}")
    print(f"repos: {[r['ref'] for r in repos]}")
    created = guest.json("POST", "/runs", json={"repo": {"kind": "demo", "ref": args.repo},
                                                "request": args.request, "options": {"auto": False}})
    run_id = created["run_id"]
    print(f"run {run_id} started")
    finished, types = stream(guest, run_id, deadline)
    detail = guest.json("GET", f"/runs/{run_id}")
    coins = detail["run"]["coins"]
    print(f"run.finished: status={finished.get('status')} summary={finished.get('summary')!r}")
    print(f"events: {dict(types)}")
    print(f"counterexamples: {len(detail['counterexamples'])}, coins: {coins}")
    if finished.get("status") not in TERMINAL:
        print("FAIL not a terminal status")
        return 1
    if health.get("bob_mode") == "replay" and coins != 0:
        print("FAIL a replay run spent Bobcoins")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
