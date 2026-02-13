import json
import logging
import time
from typing import Any, Dict, Optional
from colorama import Fore
from ollama import Client
from config import DEFAULT_MODEL, HEARTBEAT_INTERVAL_SECONDS, OLLAMA_HOST, __version__, BANNER
from local_model_wrapper import LocalModel
from memory_system import MemoryManager
from skill_registry import SkillRegistry
from heartbeat_protocol import HeartbeatProtocol
from attention_mechanism import AttentionManager
from builtin_skills import (
    CoreMemoryUpdateSkill, CoreMemoryReadSkill, ArchivalWriteSkill,
    ArchivalSearchSkill, RecallBufferSkill
)
from server_management import ensure_server
from mindroot import MindrootGemma
from Utils import c
from ollama import Message

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  NEXUSS AGENT (MAIN CLASS)
# ══════════════════════════════════════════════════════════════════════════════

class NexussAgent:
    """
    Nexuss Agent - Open CLAW Architecture.
    Heartbeat-driven autonomous operation with hierarchical memory.
    """

    DEFAULT_PERSONA = """I am Nexuss, an autonomous AI assistant with persistent memory.
I remember conversations and learn over time. I operate on a heartbeat protocol."""

    def __init__(self, model_name: str = DEFAULT_MODEL, heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
                 local_model_path: Optional[str] = None, enable_mindroot: bool = False):
        self.agent_id = "nexuss_main"
        self.model_name = model_name
        self.heartbeat_interval = heartbeat_interval
        self.local_model_path = local_model_path
        self.enable_mindroot = enable_mindroot

        if local_model_path:
            # Use local Transformers model
            self.llm = LocalModel(local_model_path)
            self.client = None
        else:
            # Use Ollama client (original behavior)
            self.client = Client(host=OLLAMA_HOST)
            self.llm = self.client

        self.memory = MemoryManager(self.agent_id)
        self.skills = SkillRegistry()
        self._register_builtin_skills()
        self.attention = AttentionManager(self.memory)
        self.heartbeat = HeartbeatProtocol(
            llm=self.llm,
            model_name=self.model_name,
            memory=self.memory,
            skills=self.skills,
            attention=self.attention,
            interval=self.heartbeat_interval
        )
        if not self.memory.core:
            self.memory.update_core_memory("persona", self.DEFAULT_PERSONA)
            self.memory.update_core_memory("user_info", "User info not provided yet.")

        # Mindroot: stochastic background thought generator
        if enable_mindroot:
            self.mindroot = MindrootGemma(
                llm=self.llm,
                min_interval=45,
                max_interval=90,
                callback=self._inject_thought,
            )
            self.heartbeat.set_mindroot(self.mindroot)
        else:
            self.mindroot = None

        logger.info(f"NexussAgent initialized (model: {model_name}, mindroot={enable_mindroot})")

    def _register_builtin_skills(self) -> None:
        self.skills.register(CoreMemoryUpdateSkill(self.memory))
        self.skills.register(CoreMemoryReadSkill(self.memory))
        self.skills.register(ArchivalWriteSkill(self.memory))
        self.skills.register(ArchivalSearchSkill(self.memory))
        self.skills.register(RecallBufferSkill(self.memory))

    def _inject_thought(self, thought) -> None:
        """Callback from Mindroot: inject thought into recall buffer."""
        self.memory.add_to_recall(Message(
            role="system",
            content=f"[internal thought] {thought.content}"
        ))
        logger.info(f"Mindroot thought: {thought.content}")

    def start(self) -> None:
        if self.client is not None:
            ensure_server(self.client)
        self.heartbeat.start()
        if self.mindroot:
            self.mindroot.start()
        logger.info("Nexuss Agent started")

    def stop(self) -> None:
        if self.mindroot:
            self.mindroot.stop()
        self.heartbeat.stop()
        logger.info("Nexuss Agent stopped")

    def send_message(self, message: str) -> None:
        self.heartbeat.send_user_input(message)

    def get_response(self, timeout: float = 30.0) -> Optional[str]:
        # Local model inference can be slow on CPU — use longer timeout
        if self.local_model_path:
            timeout = max(timeout, 300.0)
        deadline = time.time() + timeout
        responses = []
        while time.time() < deadline:
            output = self.heartbeat.get_output(timeout=0.5)
            if output:
                msg_type, content = output
                if msg_type == "message":
                    responses.append(content)
                elif msg_type == "error":
                    return f"[Error] {content}"
            elif responses:
                break
        return "\n".join(responses) if responses else None

    def chat(self, message: str) -> str:
        self.send_message(message)
        return self.get_response() or "[No response]"

    def get_status(self) -> Dict[str, Any]:
        status = {
            "agent_id": self.agent_id, "model": self.model_name,
            "version": __version__, "heartbeat": self.heartbeat.get_status(),
            "mindroot": self.mindroot is not None,
        }
        if self.mindroot:
            status["mindroot_thoughts"] = len(self.mindroot.thought_history)
            recent = self.mindroot.get_recent_thoughts(1)
            if recent:
                status["mindroot_last_topic"] = recent[0].topic
                status["mindroot_last_thought"] = recent[0].content
        return status

    def interactive_session(self) -> None:
        print(c(BANNER, Fore.CYAN))
        print(c("Type 'exit' to quit | 'status' | 'memory' | 'core' | 'skills'\n", Fore.YELLOW))
        self.start()
        try:
            while True:
                try:
                    user_input = input(c("You > ", Fore.GREEN)).strip()
                except (EOFError, KeyboardInterrupt):
                    print(c("\n[Nexuss] Goodbye!", Fore.MAGENTA))
                    break
                if not user_input:
                    continue
                cmd = user_input.lower()
                if cmd == "exit":
                    print(c("[Nexuss] Goodbye!", Fore.MAGENTA))
                    break
                elif cmd == "status":
                    print(c("\n=== Status ===", Fore.CYAN))
                    print(json.dumps(self.get_status(), indent=2, default=str))
                    continue
                elif cmd == "memory":
                    print(c("\n=== Memory ===", Fore.CYAN))
                    for k, v in self.memory.get_memory_stats().items():
                        print(f"  {k}: {v}")
                    continue
                elif cmd == "core":
                    print(c("\n=== Core Memory ===", Fore.CYAN))
                    print(self.memory.get_core_memory())
                    continue
                elif cmd == "skills":
                    print(c("\n=== Skills ===", Fore.CYAN))
                    for s in self.skills.list_skills():
                        print(f"  • {s.name}: {s.description}")
                    continue
                elif cmd == "thoughts":
                    if self.mindroot:
                        thoughts = self.mindroot.get_recent_thoughts(5)
                        print(c("\n=== Recent Thoughts ===", Fore.CYAN))
                        for t in thoughts:
                            print(f"  [{t.topic}] {t.content}")
                        if not thoughts:
                            print("  (no thoughts yet)")
                    else:
                        print(c("Mindroot not enabled. Use --mindroot flag.", Fore.YELLOW))
                    continue
                print(c("\nNexuss > ", Fore.CYAN), end="", flush=True)
                self.send_message(user_input)
                deadline = time.time() + 60.0
                got_response = False
                while time.time() < deadline:
                    output = self.heartbeat.get_output(timeout=0.2)
                    if output:
                        msg_type, content = output
                        if msg_type == "message":
                            for char in content:
                                print(c(char, Fore.WHITE), end="", flush=True)
                                time.sleep(0.01)
                            got_response = True
                        elif msg_type == "error":
                            print(c(f"[Error] {content}", Fore.RED))
                    elif got_response:
                        break
                print("\n")
        finally:
            self.stop()