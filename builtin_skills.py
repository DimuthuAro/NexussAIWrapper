
import queue
import threading
import logging
from enums_and_dataclasses import SkillCategory, SkillResult
from memory_system import MemoryManager
from skills_tools_framework import Skill
from Utils import truncate

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  BUILT-IN SKILLS
# ══════════════════════════════════════════════════════════════════════════════
class CoreMemoryUpdateSkill(Skill):
    name = "core_memory_update"
    description = "Update core memory (persona/user info)"
    category = SkillCategory.MEMORY
    parameters = {
        "key": {"type": "string", "description": "Memory key"},
        "content": {"type": "string", "description": "New content"}
    }
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    def execute(self, key: str, content: str) -> SkillResult:
        ok = self.memory.update_core_memory(key, content)
        return SkillResult(success=ok, output=f"Core '{key}' updated" if ok else "Limit exceeded")

class CoreMemoryReadSkill(Skill):
    name = "core_memory_read"
    description = "Read core memory contents"
    category = SkillCategory.MEMORY
    parameters = {}
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    def execute(self) -> SkillResult:
        return SkillResult(success=True, output=self.memory.get_core_memory())

class ArchivalWriteSkill(Skill):
    name = "archival_memory_write"
    description = "Save to long-term archival memory"
    category = SkillCategory.MEMORY
    parameters = {
        "content": {"type": "string", "description": "Content to archive"},
        "tags": {"type": "string", "description": "Comma-separated tags"}
    }
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    def execute(self, content: str, tags: str = "") -> SkillResult:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        bid = self.memory.add_to_archival(content, tag_list)
        return SkillResult(success=True, output=f"Archived: {bid}")

class ArchivalSearchSkill(Skill):
    name = "archival_memory_search"
    description = "Search archival memory"
    category = SkillCategory.MEMORY
    parameters = {
        "query": {"type": "string", "description": "Search query"},
        "tags": {"type": "string", "description": "Optional tags filter"}
    }
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    def execute(self, query: str, tags: str = "") -> SkillResult:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] or None
        results = self.memory.search_archival(query, tags=tag_list)
        if not results:
            return SkillResult(success=True, output="No matches found.")
        out = f"Found {len(results)} results:\n"
        for i, b in enumerate(results[:10], 1):
            out += f"{i}. [{b.id}] {truncate(b.content,150)}\n"
        return SkillResult(success=True, output=out)

class RecallBufferSkill(Skill):
    name = "recall_buffer_read"
    description = "Read recent conversation history"
    category = SkillCategory.MEMORY
    parameters = {"limit": {"type": "integer", "description": "Max messages"}}
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    def execute(self, limit: int = 20) -> SkillResult:
        msgs = self.memory.get_recall_messages(limit)
        if not msgs:
            return SkillResult(success=True, output="Recall empty.")
        out = f"Last {len(msgs)} messages:\n"
        for m in msgs:
            out += f"[{m.role.upper()}] {truncate(m.content or '', 100)}\n"
        return SkillResult(success=True, output=out)

class SendMessageSkill(Skill):
    name = "send_message"
    description = "Send message to user"
    category = SkillCategory.SYSTEM
    parameters = {"message": {"type": "string", "description": "Message content"}}
    def __init__(self, output_queue: queue.Queue):
        self.output_queue = output_queue
    def execute(self, message: str) -> SkillResult:
        self.output_queue.put(("message", message))
        return SkillResult(success=True, output="Sent.")

class RequestHeartbeatSkill(Skill):
    name = "request_heartbeat"
    description = "Request another thinking cycle"
    category = SkillCategory.SYSTEM
    parameters = {"reason": {"type": "string", "description": "Reason"}}
    def __init__(self, heartbeat_flag: threading.Event):
        self.heartbeat_flag = heartbeat_flag
    def execute(self, reason: str = "") -> SkillResult:
        self.heartbeat_flag.set()
        logger.info(f"Heartbeat requested: {reason}")
        return SkillResult(success=True, output=f"Heartbeat scheduled: {reason}")
