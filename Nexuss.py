#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗███████╗                        ║
║   ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝██╔════╝                        ║
║   ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗███████╗                        ║
║   ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║╚════██║                        ║
║   ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║███████║                        ║
║   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝                        ║
║                                                                               ║
║   OPEN CLAW ARCHITECTURE - Heartbeat-Driven Autonomous Agent                 ║
║   Memory • Skills • Attention • Heartbeat Protocol                           ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Nexuss Agent v2.0.0 - Professional Autonomous LLM Agent with:
  • Heartbeat Protocol (configurable interval, default 60s)
  • Hierarchical Memory System (Core, Recall, Archival)
  • Skills/Tools Framework with dynamic registration
  • Attention Mechanism for context window management
  • Self-reflection and autonomous task execution
  • Persistent state across sessions

Author: Nexuss Development Team
License: MIT
"""

from __future__ import annotations
git pull 
import warnings
warnings.filterwarnings("ignore", message=".*optree.*", category=FutureWarning)

import subprocess
import sys
import time
import os
import json
import logging
import threading
import queue
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import deque

# Local model inference imports
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# ══════════════════════════════════════════════════════════════════════════════
#  COLORAMA SETUP
# ══════════════════════════════════════════════════════════════════════════════
try:
    from colorama import init as colorama_init, Fore, Style, Back
    colorama_init(autoreset=True)
    COLOR_ENABLED = True
except ImportError:
    class _DummyColor:
        def __getattr__(self, _: str) -> str:
            return ""
    Fore = _DummyColor()
    Style = _DummyColor()
    Back = _DummyColor()
    COLOR_ENABLED = False

# ══════════════════════════════════════════════════════════════════════════════
#  OLLAMA IMPORTS
# ══════════════════════════════════════════════════════════════════════════════
from ollama import (
    Client,
    ChatResponse,
    GenerateResponse,
    ListResponse,
    Message,
    Options,
    ShowResponse,
    RequestError,
    ResponseError,
    Tool,
)

from config import DEFAULT_MODEL, HEARTBEAT_INTERVAL_SECONDS, LOG_PATH, __version__, __codename__
from skill_registry import SkillRegistry
from server_management import ensure_server
from nexuss_agent import NexussAgent
from memory_system import MemoryManager

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")]
)
logger = logging.getLogger("Nexuss")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Nexuss Agent - Open CLAW Architecture")
    parser.add_argument("-m", "--model", type=str, default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--heartbeat", type=float, default=HEARTBEAT_INTERVAL_SECONDS, help="Heartbeat interval (seconds)")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("-p", "--prompt", type=str, help="Single prompt mode")
    parser.add_argument("--local-model", type=str, help="Path to local Hugging Face model directory")
    parser.add_argument("--mindroot", action="store_true", help="Enable stochastic background thought generation")
    args = parser.parse_args()

    if args.version:
        print(f"Nexuss Agent v{__version__} ({__codename__})")
        sys.exit(0)

    agent = NexussAgent(
        model_name=args.model,
        heartbeat_interval=args.heartbeat,
        local_model_path=args.local_model,
        enable_mindroot=args.mindroot,
    )

    if args.status:
        if agent.client is not None:
            ensure_server(agent.client)
        print(json.dumps(agent.get_status(), indent=2, default=str))
        sys.exit(0)

    if args.prompt:
        agent.start()
        try:
            print(agent.chat(args.prompt))
        finally:
            agent.stop()
        sys.exit(0)

    agent.interactive_session()

if __name__ == "__main__":
    main()