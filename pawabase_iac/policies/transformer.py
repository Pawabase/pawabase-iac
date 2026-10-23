from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, check_name, plain

STEPS = ("omit", "pick", "set", "rename", "case")


@dataclass
class Transformer(Definition):
    """Reshapes rows on their way out. Give the steps directly, or a finished ``definition``.

        Transformer("public_user", omit=["password_hash", "email"], set={"display": "{{ record.name }}"}, case="camel")

    Steps run in this order: omit, pick, set, rename, case.
    """

    kind: ClassVar[str] = "transformers"
    name: str
    definition: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    omit: list[str] | None = None
    pick: list[str] | None = None
    set: dict[str, Any] | None = None
    rename: dict[str, str] | None = None
    case: Literal["camel", "snake"] | None = None

    def __post_init__(self) -> None:
        steps = {k: getattr(self, k) for k in STEPS if getattr(self, k) is not None}
        self.definition = {**self.definition, **steps}
        super().__post_init__()

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "definition": plain(self.definition, resolve=resolve)}

    def problems(self) -> list[str]:
        out = check_name(self.name, "transformer")
        if not self.definition:
            out.append("a transformer needs at least one step (omit, pick, set, rename, case)")
        for key, value in self.definition.items():
            if key not in STEPS:
                out.append(f"unknown step {key!r} (one of {', '.join(STEPS)})")
            elif key in ("omit", "pick") and not isinstance(value, list):
                out.append(f"{key} takes a list of field names")
            elif key in ("set", "rename") and not isinstance(value, dict):
                out.append(f"{key} takes a dict")
            elif key == "case" and value not in ("camel", "snake"):
                out.append("case is 'camel' or 'snake'")
        return out
