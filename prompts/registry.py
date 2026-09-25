"""
Prompt registry: loads versioned YAML prompt definitions.
Supports get, rollback, and active-version tracking.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from dataclasses import dataclass


PROMPTS_DIR = Path(__file__).parent


@dataclass
class PromptDef:
    id: str
    version: int
    system: str
    few_shot: list[dict]
    output_schema: str | None = None
    previous_version: int | None = None
    rollback_to: int | None = None

    def render(self, **kwargs) -> str:
        return self.system.format(**kwargs)


class PromptRegistry:
    def __init__(self):
        self._prompts: dict[str, dict[int, PromptDef]] = {}
        self._active: dict[str, int] = {}
        self._load_all()

    def _load_all(self):
        for path in PROMPTS_DIR.glob("*.yaml"):
            with open(path) as f:
                data = yaml.safe_load(f)
            p = PromptDef(
                id=data["id"],
                version=data["version"],
                system=data["system"],
                few_shot=data.get("few_shot", []),
                output_schema=data.get("output_schema"),
                previous_version=data.get("previous_version"),
                rollback_to=data.get("rollback_to"),
            )
            self._prompts.setdefault(p.id, {})[p.version] = p
            self._active[p.id] = p.version

    def get(self, prompt_id: str, **kwargs) -> str:
        version = self._active.get(prompt_id)
        if version is None:
            raise KeyError(f"No prompt registered: {prompt_id}")
        p = self._prompts[prompt_id][version]
        return p.render(**kwargs) if kwargs else p.system

    def rollback(self, prompt_id: str) -> int:
        version = self._active[prompt_id]
        p = self._prompts[prompt_id][version]
        target = p.rollback_to or p.previous_version
        if not target:
            raise ValueError(f"No rollback target for {prompt_id} v{version}")
        self._active[prompt_id] = target
        return target


registry = PromptRegistry()