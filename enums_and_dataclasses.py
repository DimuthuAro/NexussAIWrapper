from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from config import ATTENTION_WINDOW_TOKENS
from Utils import timestamp
# ══════════════════════════════════════════════════════════════════════════════
#  ENUMS & DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

class AgentState(Enum):
    INITIALIZING = auto()
    WAITING_INPUT = auto()
    HEARTBEAT = auto()
    ERROR = auto()
    SHUTDOWN = auto()
    IDLE = auto()
    THINKING = auto()
    EXECUTING = auto()
    

class MemoryType(Enum):
    CORE = "core"
    RECALL = "recall"
    ARCHIVAL = "archival"

class SkillCategory(Enum):
    MEMORY = "memory"
    SYSTEM = "system"
    UTILITY = "utility"
    CUSTOM = "custom"

@dataclass
class MemoryBlock:
    id: str
    content: str
    memory_type: MemoryType
    created_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)
    importance: float = 0.5
    access_count: int = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "content": self.content,
            "memory_type": self.memory_type.value,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "importance": self.importance, "access_count": self.access_count,
            "tags": self.tags,
        }

@dataclass
class HeartbeatEvent:
    beat_id: int
    timestamp: str
    state: AgentState
    memory_usage: Dict[str, int]
    pending_tasks: int
    notes: str = ""

@dataclass
class AttentionContext:
    total_tokens: int = 0
    core_tokens: int = 0
    recall_tokens: int = 0
    system_tokens: int = 0
    available_tokens: int = ATTENTION_WINDOW_TOKENS
    focus_topic: Optional[str] = None
    priority_memories: List[str] = field(default_factory=list)

@dataclass
class SkillResult:
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: float = 0.0