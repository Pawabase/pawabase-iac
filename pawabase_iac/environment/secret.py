from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from ..core.base import Definition, plain

SECRET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


@dataclass
class Secret(Definition):
    """A secret flows read with `blocks.secret.get(name=...)`. The value comes from your shell or `.env` when you deploy, never from the code.

        Secret("PAYSTACK_SECRET_KEY", value=env("PAYSTACK_SECRET_KEY"), description="Charges and refunds")

    The server never returns a value, so a secret is sent when it is new (or with `--force-secrets`), not compared.
    """

    kind: ClassVar[str] = "secrets"
    write_only: ClassVar[tuple[str, ...]] = ("value",)
    name: str
    value: Any = None
    description: str = ""

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {"name": self.name, "value": plain(self.value, resolve=resolve), "description": self.description}

    def problems(self) -> list[str]:
        out = []
        if not SECRET_NAME.match(self.name):
            out.append(f"secret name {self.name!r}: letters, digits and underscores, starting with a letter")
        if self.value is None:
            out.append("give value=env('NAME') so the value is read when you deploy")
        return out
