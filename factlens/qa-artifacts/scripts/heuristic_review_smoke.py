from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    logs_dir = repo_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "backend-heuristic-smoke.out.log"
    stderr_path = logs_dir / "backend-heuristic-smoke.err.log"

    env = os.environ.copy()
    env["FACTLENS_LLM_PROVIDER"] = "auto"
    env["NVIDIA_API_KEY"] = ""
    env["GOOGLE_API_KEY"] = ""
    env["OPENAI_API_KEY"] = ""

    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8010",
            ],
            cwd=str(backend_dir),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )

        try:
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    health = requests.get("http://127.0.0.1:8010/health", timeout=2)
                    if health.ok:
                        break
                except Exception:
                    time.sleep(0.5)
            else:
                print("Heuristic smoke server did not start in time.", file=sys.stderr)
                return 1

            response = requests.post(
                "http://127.0.0.1:8010/analyze",
                json={"text": "Mars has two moons named Phobos and Deimos."},
                timeout=120,
            )
            reports = requests.get("http://127.0.0.1:8010/reports", timeout=30).json()
            has_review_required = '"type": "review_required"' in response.text
            has_done = '"type": "done"' in response.text

            print(f"STATUS {response.status_code}")
            print(f"HAS_REVIEW_REQUIRED {has_review_required}")
            print(f"HAS_DONE {has_done}")
            print(f"REPORT_COUNT {len(reports.get('reports', []))}")
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
