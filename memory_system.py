import threading
import time
import json
import logging
from pathlib import Path
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from ollama import Message
from config import RECALL_MEMORY_LIMIT, CORE_MEMORY_LIMIT, ARCHIVAL_SEARCH_LIMIT, MEMORY_PATH, ARCHIVAL_PATH
from enums_and_dataclasses import MemoryBlock, MemoryType
from Utils import timestamp, hash_content, truncate

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  MEMORY SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
class MemoryManager:
    """Hierarchical Memory: Core (always in context), Recall (recent), Archival (long-term)."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.core: Dict[str, MemoryBlock] = {}
        self.recall: deque[Message] = deque(maxlen=RECALL_MEMORY_LIMIT)
        self.archival_index: Dict[str, MemoryBlock] = {}
        self._lock = threading.RLock()
        self._load_persistent_memory()

    def get_core_memory(self) -> str:
        with self._lock:
            parts = []
            for key, block in self.core.items():
                parts.append(f"[{key.upper()}]\n{block.content}")
                block.access_count += 1
            return "\n\n".join(parts)

    def update_core_memory(self, key: str, content: str) -> bool:
        with self._lock:
            total_len = sum(len(b.content) for k, b in self.core.items() if k != key)
            if total_len + len(content) > CORE_MEMORY_LIMIT:
                logger.warning(f"Core memory limit exceeded for '{key}'")
                return False
            if key in self.core:
                self.core[key].content = content
                self.core[key].updated_at = timestamp()
            else:
                self.core[key] = MemoryBlock(
                    id=f"core_{key}_{hash_content(content)}",
                    content=content, memory_type=MemoryType.CORE, importance=1.0
                )
            self._save_core_memory()
            logger.info(f"Core memory updated: {key}")
            return True

    def delete_core_memory(self, key: str) -> bool:
        with self._lock:
            if key in self.core:
                del self.core[key]
                self._save_core_memory()
                return True
            return False

    def add_to_recall(self, message: Message) -> None:
        with self._lock:
            self.recall.append(message)

    def get_recall_messages(self, limit: Optional[int] = None) -> List[Message]:
        with self._lock:
            msgs = list(self.recall)
            return msgs[-limit:] if limit else msgs

    def clear_recall(self) -> None:
        with self._lock:
            self.recall.clear()

    def add_to_archival(self, content: str, tags: Optional[List[str]] = None, importance: float = 0.5) -> str:
        with self._lock:
            block_id = f"arch_{hash_content(content)}_{int(time.time())}"
            block = MemoryBlock(
                id=block_id, content=content, memory_type=MemoryType.ARCHIVAL,
                tags=tags or [], importance=importance
            )
            self.archival_index[block_id] = block
            self._save_archival_block(block)
            logger.info(f"Archival added: {truncate(content, 50)}")
            return block_id

    def search_archival(self, query: str, limit: int = ARCHIVAL_SEARCH_LIMIT, tags: Optional[List[str]] = None) -> List[MemoryBlock]:
        with self._lock:
            results = []
            query_lower = query.lower()
            query_words = set(query_lower.split())
            for block in self.archival_index.values():
                if tags and not any(t in block.tags for t in tags):
                    continue
                content_lower = block.content.lower()
                score = sum(1 for w in query_words if w in content_lower)
                if score > 0:
                    block.access_count += 1
                    results.append((score, block))
            results.sort(key=lambda x: (x[0], x[1].importance), reverse=True)
            return [r[1] for r in results[:limit]]

    def delete_archival(self, block_id: str) -> bool:
        with self._lock:
            if block_id in self.archival_index:
                del self.archival_index[block_id]
                arch_file = ARCHIVAL_PATH / f"{block_id}.json"
                if arch_file.exists():
                    arch_file.unlink()
                return True
            return False

    def get_memory_stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "core_characters": sum(len(b.content) for b in self.core.values()),
                "core_limit": CORE_MEMORY_LIMIT,
                "recall_messages": len(self.recall),
                "recall_limit": RECALL_MEMORY_LIMIT,
                "archival_blocks": len(self.archival_index),
            }

    def _save_core_memory(self) -> None:
        core_file = MEMORY_PATH / f"{self.agent_id}_core.json"
        with open(core_file, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in self.core.items()}, f, indent=2)

    def _save_archival_block(self, block: MemoryBlock) -> None:
        arch_file = ARCHIVAL_PATH / f"{block.id}.json"
        with open(arch_file, "w", encoding="utf-8") as f:
            json.dump(block.to_dict(), f, indent=2)

    def _load_persistent_memory(self) -> None:
        core_file = MEMORY_PATH / f"{self.agent_id}_core.json"
        if core_file.exists():
            try:
                with open(core_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, val in data.items():
                        self.core[key] = MemoryBlock(
                            id=val["id"], content=val["content"],
                            memory_type=MemoryType.CORE,
                            created_at=val.get("created_at", timestamp()),
                            updated_at=val.get("updated_at", timestamp()),
                            importance=val.get("importance", 1.0),
                            access_count=val.get("access_count", 0),
                            tags=val.get("tags", [])
                        )
                logger.info(f"Loaded {len(self.core)} core memory blocks")
            except Exception as e:
                logger.error(f"Failed to load core memory: {e}")

        for arch_file in ARCHIVAL_PATH.glob("arch_*.json"):
            try:
                with open(arch_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    block = MemoryBlock(
                        id=data["id"], content=data["content"],
                        memory_type=MemoryType.ARCHIVAL,
                        created_at=data.get("created_at", timestamp()),
                        updated_at=data.get("updated_at", timestamp()),
                        importance=data.get("importance", 0.5),
                        access_count=data.get("access_count", 0),
                        tags=data.get("tags", [])
                    )
                    self.archival_index[block.id] = block
            except Exception as e:
                logger.error(f"Failed to load archival {arch_file}: {e}")
        logger.info(f"Loaded {len(self.archival_index)} archival blocks")

            