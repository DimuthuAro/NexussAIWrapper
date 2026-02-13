import threading
import time
import logging
from typing import Dict, Optional, List, Any
from enums_and_dataclasses import SkillResult
from skills_tools_framework import Skill

logger = logging.getLogger(__name__)

class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.RLock()

    def register(self, skill: Skill) -> None:
        with self._lock:
            self._skills[skill.name] = skill
            logger.info(f"Skill registered: {skill.name}")

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name in self._skills:
                del self._skills[name]
                logger.info(f"Skill unregistered: {name}")
                return True
            return False

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        return list(self._skills.values())

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        return [s.to_tool_schema() for s in self._skills.values()]

    def execute(self, name: str, **kwargs) -> SkillResult:
        skill = self.get(name)
        if not skill:
            return SkillResult(success=False, output=None, error=f"Skill '{name}' not found")
        start = time.time()
        try:
            result = skill.execute(**kwargs)
            result.execution_time = time.time() - start
            return result
        except Exception as e:
            logger.error(f"Skill error [{name}]: {e}")
            return SkillResult(success=False, output=None, error=str(e), execution_time=time.time()-start)
