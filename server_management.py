import subprocess
import time
import sys
import logging
from colorama import Fore, Style
from ollama import Client, ResponseError, ListResponse
from config import OLLAMA_HOST, SERVER_STARTUP_TIMEOUT

logger = logging.getLogger(__name__)

def c(text: str, color: str = "") -> str:
    """Colorize text if color support is enabled."""
    if not color:
        return str(text)
    reset = getattr(Style, 'RESET_ALL', '')
    return f"{color}{text}{reset}"

# ══════════════════════════════════════════════════════════════════════════════
#  SERVER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
def is_ollama_running() -> bool:
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Process -Name ollama -ErrorAction SilentlyContinue"],
            capture_output=True, text=True, timeout=10
        )
        return "ollama" in result.stdout.lower()
    except Exception:
        return False

def start_ollama_server() -> None:
    subprocess.Popen(["powershell", "-Command", "Start-Process ollama -ArgumentList 'serve' -NoNewWindow"])
    print(c("[Nexuss] Ollama server starting...", Fore.YELLOW))

def wait_for_server(client: Client, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client.list()
            return True
        except Exception:
            time.sleep(1)
    return False

def ensure_server(client: Client) -> None:
    if is_ollama_running():
        print(c("[Nexuss] Ollama process detected.", Fore.GREEN))
    else:
        print(c("[Nexuss] Ollama not running — launching...", Fore.YELLOW))
        start_ollama_server()
    if not wait_for_server(client):
        print(c("[Nexuss] ERROR: Could not connect to Ollama.", Fore.RED))
        sys.exit(1)
    print(c("[Nexuss] Server ready.\n", Fore.GREEN))

def list_models(client: Client) -> ListResponse:
    return client.list()

def print_models(models: ListResponse) -> None:
    print("┌─────────────────────────────────────────────────┐")
    print("│            Available Ollama Models              │")
    print("├─────────────────────────────────────────────────┤")
    for m in models.models or []:
        size_mb = (m.size or 0) / (1024 * 1024)
        name = m.model if m and m.model else "<unknown>"
        print(f"│  {name:<30} {size_mb:>8.1f} MB  │")
    print("└─────────────────────────────────────────────────┘")

def model_exists(client: Client, name: str) -> bool:
    models = list_models(client)
    for m in models.models or []:
        if m and m.model:
            if m.model == name or m.model.startswith(name.split(":")[0]):
                return True
    return False

def pull_model(client: Client, name: str) -> bool:
    print(f"[Nexuss] Pulling '{name}'...")
    try:
        for p in client.pull(name, stream=True):
            if p.total and p.completed:
                pct = p.completed / p.total * 100
                print(f"\r  {p.status}: {pct:5.1f}%", end="", flush=True)
            else:
                print(f"\r  {p.status}", end="", flush=True)
        print("\n[Nexuss] Pull complete.")
        return True
    except ResponseError as e:
        print(f"\n[Nexuss] Pull failed: {e}")
        return False