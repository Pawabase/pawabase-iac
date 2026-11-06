from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from ..core.base import Definition
from ..policies.check import reference_problems
from ..core.base import plain


@dataclass
class KnowledgeBase(Definition):
    """Documents an agent can answer from: they are split, embedded and searched by meaning and by words.

        KnowledgeBase("help", embedding_model="embed", policy="authenticated")

    The documents themselves are data, added with the SDK's ``ai.knowledge.add`` (or Studio), not defined in code.
    ``embedding_model`` is an embedding model of the environment; it can't change once documents have been read with it.
    """

    kind: ClassVar[str] = "knowledge-bases"
    name: str
    embedding_model: str = ""
    description: str = ""
    #: Who may search it.
    policy: Any = "service"
    chunk_size: int = 1200
    chunk_overlap: int = 150

    def problems(self) -> list[str]:
        out: list[str] = []
        if not re.match(r"^[a-z][a-z0-9_-]{0,59}$", str(self.name)):
            out.append(f"knowledge base {self.name!r} is not a valid name (lower-case letters, digits, _ and -, starting with a letter)")
        if not self.embedding_model:
            out.append("embedding_model names an embedding model of the environment")
        if not 200 <= self.chunk_size <= 8000:
            out.append("chunk_size is between 200 and 8000")
        if not 0 <= self.chunk_overlap <= 2000:
            out.append("chunk_overlap is between 0 and 2000")
        if self.chunk_overlap >= self.chunk_size:
            out.append("chunk_overlap must be smaller than chunk_size")
        out += reference_problems(plain(self.policy, resolve=False), "policy")
        return out
