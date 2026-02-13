from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
from enums_and_dataclasses import SkillCategory, SkillResult
# ══════════════════════════════════════════════════════════════════════════════
#  SKILLS / TOOLS FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════
class Skill(ABC):
    name: str = "base_skill"
    description: str = "Base skill"
    category: SkillCategory = SkillCategory.CUSTOM
    parameters: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> SkillResult:
        pass

    def to_tool_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys())
                }
            }
        }
