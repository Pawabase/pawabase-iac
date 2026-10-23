from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..core.base import Definition, check_name, plain
from .check import field_problems


@dataclass
class Schema(Definition):
    """A reusable shape of data, used by ``Ref`` fields and by routes as ``input_schema`` / ``response_schema``."""

    kind: ClassVar[str] = "schemas"
    name: str
    fields: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "fields": plain(self.fields, resolve=resolve)}

    def problems(self) -> list[str]:
        return check_name(self.name, "schema", re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")) + field_problems(self.fields)
