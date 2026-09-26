"""A fake `bob` executable for unit tests. It never calls the network and costs no coins.

Env:
  FAKE_BOB_SCENARIO  comma-separated fixture names; call N plays item N (the last item repeats),
                     or "sleep" to hang (spawns a child `sleep` and writes its pid to FAKE_BOB_CHILD_PID)
  FAKE_BOB_STATE     a file that counts invocations
  FAKE_BOB_ARGV_LOG  a file that gets one JSON line per call: argv plus a few env checks
Placeholders in fixtures: {WORKSPACE} (the --workspace value) and {KEY} (the BOB_API_KEY env value).
"""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def main() -> None:
    # bob hangs forever on an open stdin, so the real client must pass DEVNULL (a character device).
    if not stat.S_ISCHR(os.fstat(0).st_mode) or sys.stdin.read() != "":
        emit({"type": "result", "status": "stdin_not_devnull", "stats": {"session_costs": 0}})
        return
    argv = sys.argv[1:]
    workspace = argv[argv.index("--workspace") + 1]
    log = os.environ.get("FAKE_BOB_ARGV_LOG")
    if log:
        with open(log, "a") as fh:
            fh.write(json.dumps({
                "argv": argv,
                "has_key": bool(os.environ.get("BOB_API_KEY")),
                "path": os.environ.get("PATH", ""),
                "cwd": os.getcwd(),
                "env_keys": sorted(os.environ),
            }) + "\n")
    state = Path(os.environ.get("FAKE_BOB_STATE", "/dev/null"))
    count = int(state.read_text() or 0) if state.is_file() else 0
    if state.name != "null":
        state.write_text(str(count + 1))
    scenarios = os.environ.get("FAKE_BOB_SCENARIO", "ok").split(",")
    scenario = scenarios[min(count, len(scenarios) - 1)]
    if scenario == "sleep":
        child = subprocess.Popen(["sleep", "60"])
        Path(os.environ["FAKE_BOB_CHILD_PID"]).write_text(str(child.pid))
        time.sleep(60)
        return
    key = os.environ.get("BOB_API_KEY", "")
    for line in (FIXTURES / f"{scenario}.ndjson").read_text().splitlines():
        if line.strip():
            print(line.replace("{WORKSPACE}", workspace).replace("{KEY}", key), flush=True)
            time.sleep(0.005)


if __name__ == "__main__":
    main()
