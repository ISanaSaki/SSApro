"""Team smoke check: contract tests + one practice scenario + printed summary.

Usage:
    python scripts/smoke.py [--team URL] [--seed N] [--scenario NAME] [--out DIR]
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def wait_health(team_url: str, timeout_sec: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{team_url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.0)
    return False


def run_step(label: str, args: list[str]) -> int:
    print(f"\n=== {label} ===", flush=True)
    return subprocess.run(args, cwd=ROOT).returncode


def print_summary(out_dir: Path) -> None:
    result_path = out_dir / "result.json"
    if not result_path.is_file():
        print(f"warning: {result_path} not found", file=sys.stderr)
        return
    summary = json.loads(result_path.read_text(encoding="utf-8")).get("summary", {})
    print("\n=== practice summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--scenario", default="P-normal")
    parser.add_argument("--out", default="run_out")
    args = parser.parse_args()

    team_url = args.team.rstrip("/")
    print(f"waiting for team service at {team_url} ...", flush=True)
    if not wait_health(team_url):
        print(
            "error: team service is not reachable; start it first "
            "(scripts/run.ps1 or scripts/run.sh).",
            file=sys.stderr,
        )
        return 2

    code = run_step(
        "contract tests",
        [sys.executable, "-m", "harness.contract_tests", "--team", team_url],
    )
    if code != 0:
        print("error: contract tests failed", file=sys.stderr)
        return 1

    code = run_step(
        f"scenario {args.scenario}",
        [
            sys.executable,
            "-m",
            "harness.runner",
            "--team",
            team_url,
            "--scenario",
            args.scenario,
            "--seed",
            str(args.seed),
            "--out",
            args.out,
        ],
    )
    if code != 0:
        print("error: scenario run failed", file=sys.stderr)
        return 1

    print_summary(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
