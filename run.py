"""One command to bring Callwire up:  python run.py

    python run.py               engine (API + watcher + sockets) and client UI
    python run.py --api-only    engine only; a built-in page is served at http://localhost:8000
    python run.py --no-browser  don't open a browser tab
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "engine"
CLIENT = ROOT / "client"
VENV = ENGINE / ".venv"
ENV_FILE = ENGINE / ".env"
API_PORT, UI_PORT = 8000, 5173


def read_env_value(path: Path, name: str) -> str:
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'")
    return ""


def run_checked(command: list[str], cwd: Path) -> None:
    if subprocess.run(command, cwd=cwd).returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}")


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def wait_until_ready(url: str, proc: subprocess.Popen, timeout: float = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status < 400:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def pipe_output(proc: subprocess.Popen, tag: str) -> None:
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        try:
            print(f"[{tag}] {line}", flush=True)
        except UnicodeEncodeError:  # legacy Windows consoles
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(f"[{tag}] {line.encode(enc, errors='replace').decode(enc, errors='replace')}", flush=True)


def spawn(command: list[str], cwd: Path) -> subprocess.Popen:
    return subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Callwire")
    parser.add_argument("--api-only", action="store_true", help="skip the React UI")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")

    key = read_env_value(ENV_FILE, "LLM_API_KEY")
    if not key or key.lower() in {"your_api_key", "your-api-key", "change-me", "replace-me"} or "here" in key.lower():
        print("Cannot start: engine/.env has no real LLM_API_KEY.")
        print("Copy engine/.env.example to engine/.env and set LLM_API_KEY to a valid key.")
        return 1

    python = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        print("Creating Python virtual environment...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    if not (ENGINE / ".venv-ready").exists():
        print("Installing Python dependencies...")
        run_checked([str(python), "-m", "pip", "install", "-r", "requirements.txt"], ENGINE)

    npm = None
    if not args.api_only:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            print("Cannot start the UI: npm was not found on PATH.")
            print("Install Node.js, or run `python run.py --api-only`.")
            return 1
        if not (CLIENT / "node_modules").exists():
            print("Installing frontend dependencies...")
            run_checked([npm, "install"], CLIENT)
    (ENGINE / ".venv-ready").touch()

    engine = ui = None
    if port_is_open(API_PORT):
        print(f"Reusing engine at http://localhost:{API_PORT}")
    else:
        print(f"Starting engine at http://localhost:{API_PORT}")
        engine = spawn([str(python), "-m", "uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", str(API_PORT)], ENGINE)
        if not wait_until_ready(f"http://127.0.0.1:{API_PORT}/v1/briefs", engine):
            engine.terminate()
            raise RuntimeError(f"Engine did not become ready on port {API_PORT}")

    if npm:
        if port_is_open(UI_PORT):
            print(f"Reusing UI at http://localhost:{UI_PORT}")
        else:
            print(f"Starting UI at http://localhost:{UI_PORT}")
            ui = spawn([npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(UI_PORT), "--strictPort"], CLIENT)
            if not wait_until_ready(f"http://127.0.0.1:{UI_PORT}", ui):
                ui.terminate()
                if engine:
                    engine.terminate()
                raise RuntimeError(f"UI did not become ready on port {UI_PORT}")

    for proc, tag in ((engine, "engine"), (ui, "ui")):
        if proc:
            threading.Thread(target=pipe_output, args=(proc, tag), daemon=True).start()

    home = f"http://localhost:{UI_PORT if npm else API_PORT}"
    if not args.no_browser:
        webbrowser.open(home)
    print(f"Callwire is running at {home}  (Ctrl+C to stop)")

    try:
        while True:
            if engine and engine.poll() is not None:
                raise RuntimeError(f"Engine stopped with exit code {engine.returncode}")
            if ui and ui.poll() is not None:
                raise RuntimeError(f"UI stopped with exit code {ui.returncode}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        procs = [p for p in (engine, ui) if p]
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
