#!/usr/bin/env python3
"""Nexuss Service - Background model server with heartbeat protocol."""

import warnings
warnings.filterwarnings("ignore", message=".*optree.*", category=FutureWarning)

import sys
import os
import json
import signal
import logging
import argparse
import subprocess
import shutil
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from config import DATA_DIR, __version__, __codename__
from nexuss_agent import NexussAgent

SERVICE_PORT = 7860
SERVICE_HOST = "127.0.0.1"
PID_FILE = DATA_DIR / "nexuss_service.pid"
DEFAULT_MODEL_PATH = str(Path.home() / "Desktop" / "llm" / "gemma_model")

logger = logging.getLogger("NexussService")

# ── Global state ──────────────────────────────────────────────────────────
_agent = None
_model_info = {}
_shutdown_event = threading.Event()
_chat_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP API HANDLER
# ══════════════════════════════════════════════════════════════════════════════

class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        routes = {
            "/health": lambda: {"status": "ok", "version": __version__},
            "/model-info": lambda: _model_info,
            "/status": lambda: _agent.get_status() if _agent else {},
        }
        handler = routes.get(self.path)
        if handler:
            self._json(handler())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/chat":
            body = self._body()
            msg = body.get("message", "").strip()
            if not msg:
                return self._json({"error": "empty message"}, 400)
            with _chat_lock:
                resp = _agent.chat(msg)
            self._json({"response": resp})
        elif self.path == "/shutdown":
            self._json({"status": "shutting down"})
            threading.Thread(target=lambda: (_shutdown_event.set()), daemon=True).start()
        elif self.path == "/beat":
            if _agent:
                _agent.heartbeat._heartbeat_requested.set()
                self._json({"status": "heartbeat triggered"})
            else:
                self._json({"error": "agent not ready"}, 503)
        elif self.path == "/thought":
            if _agent and _agent.mindroot:
                def _gen():
                    t = _agent.mindroot.generate_thought()
                    if _agent.mindroot.callback:
                        _agent.mindroot.callback(t)
                threading.Thread(target=_gen, daemon=True).start()
                self._json({"status": "thought triggered"})
            else:
                self._json({"error": "mindroot not active"}, 503)
        else:
            self._json({"error": "not found"}, 404)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def _json(self, data, code=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _collect_info(agent):
    import torch
    info = {
        "version": __version__,
        "codename": __codename__,
        "model_name": agent.model_name,
        "port": SERVICE_PORT,
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if agent.local_model_path and hasattr(agent.llm, "model"):
        m = agent.llm.model
        info["model_path"] = str(agent.local_model_path)
        info["device"] = str(next(m.parameters()).device)
        info["parameters"] = sum(p.numel() for p in m.parameters())
        info["vocab_size"] = agent.llm.tokenizer.vocab_size
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_total_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
            info["vram_used_gb"] = round(
                torch.cuda.memory_allocated(0) / 1024**3, 2)
            info["quantization"] = "4-bit NF4"
        else:
            info["gpu_name"] = "CPU"
            info["quantization"] = "None (float32)"
    return info


def _pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _read_pid():
    try:
        return int(PID_FILE.read_text().strip()) if PID_FILE.exists() else None
    except (ValueError, OSError):
        return None


def _is_running():
    pid = _read_pid()
    return pid is not None and _pid_alive(pid)


# ══════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

def cmd_start(args):
    global _agent, _model_info

    if _is_running():
        print(f"Already running (PID {_read_pid()})")
        return

    # Background mode: detach a new process without --background
    if args.background:
        exe = shutil.which("nexuss-service")
        cmd = [exe or sys.executable]
        if not exe:
            cmd.append(__file__)
        cmd += ["start", "--model-path", args.model_path, "--port", str(args.port)]
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
            kw["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        subprocess.Popen(cmd, **kw)
        print("Service starting in background...")
        return

    # ── Foreground mode ──────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(DATA_DIR / "service.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logger.info("Loading model from %s", args.model_path)
    _agent = NexussAgent(local_model_path=args.model_path, enable_mindroot=getattr(args, 'mindroot', False))
    _model_info = _collect_info(_agent)
    _agent.start()

    PID_FILE.write_text(str(os.getpid()))

    server = ThreadingHTTPServer((SERVICE_HOST, args.port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"\n{'='*50}")
    print(f"  Nexuss Service v{__version__}")
    print(f"  http://{SERVICE_HOST}:{args.port}")
    print(f"  Device: {_model_info.get('device', '?')}")
    print(f"  GPU: {_model_info.get('gpu_name', '?')}")
    print(f"  PID: {os.getpid()}")
    print(f"{'='*50}")
    print("Press Ctrl+C to stop\n")

    for sig_id in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig_id, lambda *_: _shutdown_event.set())

    _shutdown_event.wait()

    logger.info("Shutting down...")
    server.shutdown()
    _agent.stop()
    PID_FILE.unlink(missing_ok=True)
    print("Stopped.")


def cmd_stop(_):
    if not _is_running():
        print("Not running")
        return
    pid = _read_pid()
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://{SERVICE_HOST}:{SERVICE_PORT}/shutdown",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        print(f"Stop signal sent (PID {pid})")
    except Exception:
        os.kill(pid, signal.SIGTERM)
        print(f"Killed PID {pid}")
    PID_FILE.unlink(missing_ok=True)


def cmd_status(_):
    if not _is_running():
        print("Not running")
        return
    pid = _read_pid()
    try:
        import urllib.request
        r = urllib.request.urlopen(
            f"http://{SERVICE_HOST}:{SERVICE_PORT}/model-info", timeout=3
        )
        info = json.loads(r.read())
        print(f"Running (PID {pid})")
        for k, v in info.items():
            print(f"  {k}: {v}")
    except Exception:
        print(f"Process alive (PID {pid}) but API unreachable")


def cmd_install(args):
    exe = shutil.which("nexuss-service")
    if not exe:
        print("nexuss-service not in PATH. Install the package first.")
        return
    mp = getattr(args, "model_path", DEFAULT_MODEL_PATH)
    task = f'"{exe}" start --model-path "{mp}" --background'
    r = subprocess.run(
        ["schtasks", "/create", "/tn", "NexussService",
         "/tr", task, "/sc", "ONLOGON", "/rl", "LIMITED", "/f"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print("Registered for Windows startup (Task: NexussService)")
    else:
        print(f"Failed: {r.stderr}")


def cmd_uninstall(_):
    r = subprocess.run(
        ["schtasks", "/delete", "/tn", "NexussService", "/f"],
        capture_output=True, text=True,
    )
    print("Startup task removed" if r.returncode == 0 else f"Failed: {r.stderr}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Nexuss Service Manager")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("start", help="Start the model service")
    s.add_argument("--model-path", default=DEFAULT_MODEL_PATH,
                   help="Path to local HuggingFace model directory")
    s.add_argument("--port", type=int, default=SERVICE_PORT, help="API port")
    s.add_argument("--mindroot", action="store_true",
                   help="Enable stochastic background thought generation")
    s.add_argument("--background", action="store_true",
                   help="Run as a detached background process")

    sub.add_parser("stop", help="Stop the running service")
    sub.add_parser("status", help="Check service status")

    i = sub.add_parser("install", help="Register for Windows startup")
    i.add_argument("--model-path", default=DEFAULT_MODEL_PATH)

    sub.add_parser("uninstall", help="Remove from Windows startup")

    args = p.parse_args()
    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
    }
    handler = commands.get(args.cmd)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
