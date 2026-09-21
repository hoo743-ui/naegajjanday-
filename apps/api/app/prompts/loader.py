"""Prompt layer: versioned YAML files `<id>.v<N>.yaml`, rendered with sandboxed Jinja2.

Prompts are never inlined in services. A version can be pinned per prompt id (rollbacks / A-B);
unpinned ids resolve to the highest version on disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

PROMPT_DIR = Path(__file__).resolve().parent
_FILE_RE = re.compile(r"^(?P<id>[a-z0-9_]+)\.v(?P<version>\d+)\.ya?ml$")
_env = SandboxedEnvironment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, autoescape=False)


class PromptNotFoundError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    id: str
    version: int
    system: str
    user: str
    tier: str
    max_tokens: int
    output_schema: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class Prompt:
    id: str
    version: int
    system: str = ""
    user: str = ""
    tier: str = "smart"
    max_tokens: int = 2048
    output_schema: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)  # free-form extras (e.g. fallback phrases)

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"

    def render(self, **variables: Any) -> RenderedPrompt:
        return RenderedPrompt(
            id=self.id,
            version=self.version,
            system=_env.from_string(self.system).render(**variables).strip(),
            user=_env.from_string(self.user).render(**variables).strip(),
            tier=self.tier,
            max_tokens=self.max_tokens,
            output_schema=self.output_schema,
        )

    def render_text(self, template: str, **variables: Any) -> str:
        return _env.from_string(template).render(**variables).strip()


class PromptLoader:
    def __init__(self, directory: Path = PROMPT_DIR, pins: dict[str, int] | None = None) -> None:
        self._dir = directory
        self._pins = dict(pins or {})
        self._cache: dict[tuple[str, int], Prompt] = {}

    def versions(self, prompt_id: str) -> list[int]:
        found = []
        for path in self._dir.iterdir():
            m = _FILE_RE.match(path.name)
            if m and m["id"] == prompt_id:
                found.append(int(m["version"]))
        return sorted(found)

    def get(self, prompt_id: str, version: int | None = None) -> Prompt:
        versions = self.versions(prompt_id)
        if not versions:
            raise PromptNotFoundError(prompt_id)
        wanted = version or self._pins.get(prompt_id) or versions[-1]
        if wanted not in versions:
            raise PromptNotFoundError(f"{prompt_id}@v{wanted}")
        key = (prompt_id, wanted)
        if key not in self._cache:
            self._cache[key] = self._read(prompt_id, wanted)
        return self._cache[key]

    def _read(self, prompt_id: str, version: int) -> Prompt:
        path = next(
            p
            for p in self._dir.iterdir()
            if (m := _FILE_RE.match(p.name)) and m["id"] == prompt_id and int(m["version"]) == version
        )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if raw.get("id", prompt_id) != prompt_id or int(raw.get("version", version)) != version:
            raise ValueError(f"{path.name}: id/version in the file do not match the file name")
        known = {"id", "version", "description", "system", "user", "tier", "max_tokens", "output_schema"}
        return Prompt(
            id=prompt_id,
            version=version,
            system=str(raw.get("system") or ""),
            user=str(raw.get("user") or ""),
            tier=str(raw.get("tier") or "smart"),
            max_tokens=int(raw.get("max_tokens") or 2048),
            output_schema=raw.get("output_schema"),
            data={k: v for k, v in raw.items() if k not in known},
        )


@lru_cache
def get_prompt_loader() -> PromptLoader:
    return PromptLoader()
