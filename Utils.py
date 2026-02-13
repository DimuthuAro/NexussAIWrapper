import hashlib
import json
import logging
from colorama import Fore, Style, init
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from colorama import init as colorama_init
    colorama_init(autoreset=True)
    COLOR_ENABLED = True
except ImportError:
    COLOR_ENABLED = False

CONFIG_PATH = Path.home() / ".nexuss" / "config.json"

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def c(text: str, color: str = "") -> str:
    """Colorize text if color support is enabled."""
    if not COLOR_ENABLED or not color:
        return str(text)
    reset = getattr(Style, 'RESET_ALL', '')
    return f"{color}{text}{reset}"

def timestamp() -> str:
    return datetime.now().isoformat()

def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:12]

def truncate(text: str, max_len: int = 100) -> str:
    return text[:max_len-3] + "..." if len(text) > max_len else text

def estimate_tokens(text: str) -> int:
    return len(text) // 4

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

