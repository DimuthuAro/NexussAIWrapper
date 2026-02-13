from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
#  VERSION & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
__version__ = "2.0.0"
__codename__ = "OPEN CLAW"

# Heartbeat Configuration
HEARTBEAT_INTERVAL_SECONDS = 60  # 1 minute heartbeat
HEARTBEAT_MAX_MISSED = 3         # Max missed heartbeats before alarm
LOCAL_MODEL_TIMEOUT_SECONDS = 120  # Max generation time per request

# Memory Configuration
CORE_MEMORY_LIMIT = 2048         # Characters for core memory
RECALL_MEMORY_LIMIT = 100        # Max messages in recall buffer
ARCHIVAL_SEARCH_LIMIT = 50       # Max archival search results
ATTENTION_WINDOW_TOKENS = 4096   # Context window size estimation

# Paths
DATA_DIR = Path.home() / ".nexuss"
CONFIG_PATH = DATA_DIR / "config.json"
MEMORY_PATH = DATA_DIR / "memory"
ARCHIVAL_PATH = DATA_DIR / "archival"
SKILLS_PATH = DATA_DIR / "skills"
LOG_PATH = DATA_DIR / "nexuss.log"
STATE_PATH = DATA_DIR / "agent_state.pkl"

# Ensure directories exist
for _p in [DATA_DIR, MEMORY_PATH, ARCHIVAL_PATH, SKILLS_PATH]:
    _p.mkdir(parents=True, exist_ok=True)

# Server Configuration
DEFAULT_MODEL = "Nexuss:ds7b"
OLLAMA_HOST = "http://localhost:11434"
SERVER_STARTUP_TIMEOUT = 30

# Service Configuration
SERVICE_PORT = 7860
SERVICE_HOST = "127.0.0.1"

BANNER = r'''
╔═══════════════════════════════════════════════════════════════════════════════╗
║   ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗███████╗   OPEN CLAW v2.0.0     ║
║   ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝██╔════╝                        ║
║   ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗███████╗   Heartbeat Protocol   ║
║   ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║╚════██║   Memory • Skills      ║
║   ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║███████║   Attention Mechanism  ║
║   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
'''

SYSTEM_PROMPT = "You are Nexuss, an autonomous AI assistant with persistent memory."
TRANSCRIPT_DIR = Path.cwd() / "nexuss_sessions"
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)