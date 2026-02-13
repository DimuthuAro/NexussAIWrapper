import logging
from typing import List, Optional, Dict, Any, Tuple
from ollama import Message
from config import ATTENTION_WINDOW_TOKENS
from enums_and_dataclasses import MemoryType, AttentionContext
from memory_system import MemoryManager
from Utils import estimate_tokens, truncate

logger = logging.getLogger(__name__)
# ══════════════════════════════════════════════════════════════════════════════
#  ATTENTION MECHANISM
# ══════════════════════════════════════════════════════════════════════════════
class AttentionManager:
    """Manages context window allocation and prioritization."""

    def __init__(self, memory: MemoryManager, max_tokens: int = ATTENTION_WINDOW_TOKENS):
        self.memory = memory
        self.max_tokens = max_tokens
        self.context = AttentionContext(available_tokens=max_tokens)

    def build_context(self, system_prompt: str, focus_query: Optional[str] = None) -> tuple[List[Message], AttentionContext]:
        messages: List[Message] = []
        system_tokens = estimate_tokens(system_prompt)
        core_content = self.memory.get_core_memory()
        core_tokens = estimate_tokens(core_content)
        full_system = f"{system_prompt}\n\n### CORE MEMORY ###\n{core_content}"
        messages.append(Message(role="system", content=full_system))
        used_tokens = system_tokens + core_tokens
        remaining = self.max_tokens - used_tokens - 500

        if focus_query:
            archival_results = self.memory.search_archival(focus_query, limit=5)
            if archival_results:
                archival_parts = [f"- {truncate(b.content, 200)}" for b in archival_results]
                archival_content = "\n### RELEVANT MEMORIES ###\n" + "\n".join(archival_parts)
                archival_tokens = estimate_tokens(archival_content)
                if archival_tokens < remaining // 3:
                    messages[0] = Message(role="system", content=full_system + "\n" + archival_content)
                    used_tokens += archival_tokens
                    remaining -= archival_tokens

        recall_messages = self.memory.get_recall_messages()
        recall_to_add = []
        recall_tokens = 0
        for msg in reversed(recall_messages):
            msg_tokens = estimate_tokens(msg.content or "")
            if recall_tokens + msg_tokens > remaining:
                break
            recall_to_add.insert(0, msg)
            recall_tokens += msg_tokens
        messages.extend(recall_to_add)
        used_tokens += recall_tokens

        self.context = AttentionContext(
            total_tokens=used_tokens, core_tokens=core_tokens,
            recall_tokens=recall_tokens, system_tokens=system_tokens,
            available_tokens=self.max_tokens - used_tokens, focus_topic=focus_query
        )
        return messages, self.context

    def get_context_stats(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.context.total_tokens,
            "core_tokens": self.context.core_tokens,
            "recall_tokens": self.context.recall_tokens,
            "available_tokens": self.context.available_tokens,
            "utilization_pct": round(self.context.total_tokens / self.max_tokens * 100, 1),
            "focus_topic": self.context.focus_topic
        }
