import threading
import queue
import json
import logging
import traceback
import inspect
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from collections import deque
from ollama import ChatResponse, Message, ResponseError, RequestError
from config import HEARTBEAT_INTERVAL_SECONDS, HEARTBEAT_MAX_MISSED, LOCAL_MODEL_TIMEOUT_SECONDS
from enums_and_dataclasses import AgentState, HeartbeatEvent
from memory_system import MemoryManager
from skill_registry import SkillRegistry
from attention_mechanism import AttentionManager
from builtin_skills import RequestHeartbeatSkill, SendMessageSkill
from local_model_wrapper import LocalModel
from Utils import timestamp

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  HEARTBEAT PROTOCOL
# ══════════════════════════════════════════════════════════════════════════════

class HeartbeatProtocol:
    """
    Heartbeat-driven autonomous operation.
    Agent processes on periodic heartbeats, can request additional cycles.
    """

    HEARTBEAT_SYSTEM_PROMPT = """You are Nexuss, an autonomous AI agent with persistent memory.
You operate on a HEARTBEAT protocol. Each heartbeat:
1. Process pending user messages
2. Reflect on memory and state
3. Execute skills/tools as needed
4. Decide to continue (request_heartbeat) or wait

Memory systems:
- CORE MEMORY: Persona, key user info (always in context)
- RECALL BUFFER: Recent conversation
- ARCHIVAL MEMORY: Long-term searchable storage

Use send_message to respond. Use request_heartbeat for more processing time.

Current: {timestamp} | Heartbeat #{beat_count}
"""

    LOCAL_SYSTEM_PROMPT = """You are Nexuss, an AI agent. Answer the user helpfully and concisely.

YOU HAVE THESE INTERNAL SYSTEMS:
{status_block}

If the user asks about heartbeats, thoughts, dreams, or your internal state, use the information above to answer accurately. For example: "I have had X heartbeats so far" or "My latest thought was about Y".

Current time: {timestamp}
"""

    def __init__(self, llm, model_name: str, memory: MemoryManager,
                 skills: SkillRegistry, attention: AttentionManager,
                 interval: float = HEARTBEAT_INTERVAL_SECONDS):
        self.llm = llm
        self.model_name = model_name
        self.memory = memory
        self.skills = skills
        self.attention = attention
        self.interval = interval

        self.beat_count = 0
        self.missed_beats = 0
        self.state = AgentState.INITIALIZING
        self.last_heartbeat: Optional[datetime] = None
        self.heartbeat_history: deque[HeartbeatEvent] = deque(maxlen=100)

        self._stop_event = threading.Event()
        self._heartbeat_requested = threading.Event()
        self._user_input_queue: queue.Queue = queue.Queue()
        self._output_queue: queue.Queue = queue.Queue()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._is_local = isinstance(llm, LocalModel)
        self.mindroot = None  # Set later via set_mindroot()
        self.skills.register(SendMessageSkill(self._output_queue))
        self.skills.register(RequestHeartbeatSkill(self._heartbeat_requested))

    def start(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="HeartbeatThread")
        self._heartbeat_thread.start()
        self.state = AgentState.IDLE
        logger.info("Heartbeat protocol started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5.0)
        self.state = AgentState.SHUTDOWN
        logger.info("Heartbeat protocol stopped")

    def send_user_input(self, message: str) -> None:
        self._user_input_queue.put(message)
        self._heartbeat_requested.set()

    def get_output(self, timeout: float = 0.1) -> Optional[Tuple]:
        try:
            return self._output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _heartbeat_loop(self) -> None:
        logger.info(f"Heartbeat loop started (interval: {self.interval}s)")
        while not self._stop_event.is_set():
            try:
                triggered = self._heartbeat_requested.wait(timeout=self.interval)
                self._heartbeat_requested.clear()
                if self._stop_event.is_set():
                    break
                self._execute_heartbeat(triggered_by_event=triggered)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}\n{traceback.format_exc()}")
                self.missed_beats += 1
                if self.missed_beats >= HEARTBEAT_MAX_MISSED:
                    logger.critical("Too many missed heartbeats!")
                    self.state = AgentState.ERROR
                    


    def _execute_heartbeat(self, triggered_by_event: bool = False) -> None:
        with self._lock:
            self.beat_count += 1
            self.state = AgentState.HEARTBEAT
            self.last_heartbeat = datetime.now()
            logger.info(f"Heartbeat #{self.beat_count} executing (triggered={triggered_by_event})")

            user_messages = []
            while not self._user_input_queue.empty():
                try:
                    user_messages.append(self._user_input_queue.get_nowait())
                except queue.Empty:
                    break

            for msg in user_messages:
                self.memory.add_to_recall(Message(role="user", content=msg))

            if self._is_local:
                status_block = self._build_status_block()
                system_prompt = self.LOCAL_SYSTEM_PROMPT.format(
                    timestamp=timestamp(), status_block=status_block
                )
            else:
                system_prompt = self.HEARTBEAT_SYSTEM_PROMPT.format(
                    timestamp=timestamp(), beat_count=self.beat_count
                )
            focus = user_messages[-1] if user_messages else None
            messages, _ = self.attention.build_context(system_prompt, focus)

            if user_messages:
                if self._is_local:
                    # For local models: embed status context right with the user message
                    # so the small model actually sees it (system prompt gets too distant)
                    status_block = self._build_status_block()
                    augmented = (
                        f"[Your internal status for reference]\n{status_block}\n\n"
                        f"User message: {user_messages[-1]}"
                    )
                    messages.append(Message(role="user", content=augmented))
                else:
                    hint = "\n\n[PENDING USER INPUT]\n" + "\n".join(f"User: {m}" for m in user_messages)
                    messages.append(Message(role="user", content=f"Process these messages and respond.{hint}"))
            else:
                if self._is_local:
                    return  # Local models: skip idle heartbeats (no user input)
                messages.append(Message(role="user", content="Heartbeat tick. Reflect and act if needed."))

            self.state = AgentState.THINKING
            try:
                response = self._call_llm_chat(messages)
                self._process_response(response, messages)
            except (ResponseError, RequestError) as e:
                logger.error(f"LLM call failed: {e}")
                self._output_queue.put(("error", str(e)))
            except Exception as e:
                logger.error(f"LLM call error: {e}\n{traceback.format_exc()}")
                self._output_queue.put(("error", str(e)))

            event = HeartbeatEvent(
                beat_id=self.beat_count, timestamp=timestamp(), state=self.state,
                memory_usage=self.memory.get_memory_stats(), pending_tasks=len(user_messages),
                notes=f"triggered={triggered_by_event}"
            )
            self.heartbeat_history.append(event)
            self.state = AgentState.IDLE
            self.missed_beats = 0

    def _process_response(self, response: ChatResponse, messages: List[Message]) -> None:
        if not response.message:
            return
        self.memory.add_to_recall(Message(role="assistant", content=response.message.content or ""))

        if response.message.tool_calls:
            self.state = AgentState.EXECUTING
            for tc in response.message.tool_calls:
                func_name = tc.function.name
                func_args = tc.function.arguments or {}
                logger.info(f"Executing: {func_name}({func_args})")
                result = self.skills.execute(func_name, **func_args)
                if not result.success:
                    logger.warning(f"Skill failed: {func_name} - {result.error}")
                messages.append(Message(role="tool", content=json.dumps({
                    "name": func_name, "result": result.output if result.success else result.error
                })))

        if response.message.content and not response.message.tool_calls:
            self._output_queue.put(("message", response.message.content))

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state.name, "beat_count": self.beat_count,
            "missed_beats": self.missed_beats,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "interval_seconds": self.interval,
            "memory_stats": self.memory.get_memory_stats(),
            "attention_stats": self.attention.get_context_stats(),
            "skills": [s.name for s in self.skills.list_skills()]
        }

    def set_mindroot(self, mindroot) -> None:
        """Give heartbeat access to mindroot for status injection."""
        self.mindroot = mindroot

    def _build_status_block(self) -> str:
        """Build dynamic status info for local model context."""
        lines = [
            "HEARTBEAT PROTOCOL (your life pulse):",
            f"  My heartbeat count = {self.beat_count}",
            f"  My heartbeat state = {self.state.name}",
            f"  Heartbeat interval = every {self.interval} seconds",
            f"  Last beat at = {self.last_heartbeat.isoformat() if self.last_heartbeat else 'never'}",
        ]
        if self.mindroot:
            thoughts = self.mindroot.get_recent_thoughts(3)
            lines.append(f"MINDROOT (my dream/thought generator):")
            lines.append(f"  Mindroot is active = yes")
            lines.append(f"  Total thoughts I have generated = {len(self.mindroot.thought_history)}")
            if thoughts:
                lines.append(f"  My recent thoughts/dreams:")
                for t in thoughts:
                    lines.append(f"    Topic: {t.topic} -> \"{t.content}\"")
            else:
                lines.append("  I have no thoughts yet.")
        else:
            lines.append("MINDROOT: not active")
        return "\n".join(lines)

    def _call_llm_chat(self, messages: List[Message]) -> ChatResponse:
        chat_sig = inspect.signature(self.llm.chat)
        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }
        # Local models (Gemma etc.) don't support tool calling
        if not self._is_local:
            kwargs["tools"] = self.skills.get_tools_schema()
        if "timeout_seconds" in chat_sig.parameters:
            kwargs["timeout_seconds"] = LOCAL_MODEL_TIMEOUT_SECONDS
        return self.llm.chat(**kwargs)