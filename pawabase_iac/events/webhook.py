from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

from ..core.base import Definition, Env, check_name


@dataclass
class Webhook(Definition):
    """Calls a URL when events happen. ``secret`` signs each delivery; give it as ``env("NAME")``.

        Webhook("erp", url="https://erp.example.com/hooks/pawabase", events=["resource.orders.*"],
                secret=env("ERP_HOOK_SECRET"), headers={"x-tenant": "acme"}, max_attempts=8)
    """

    kind: ClassVar[str] = "webhooks"
    write_only: ClassVar[tuple[str, ...]] = ("secret",)
    name: str
    url: str
    events: list[str] = field(default_factory=lambda: ["*"])
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    max_attempts: int = 5
    secret: str | Env | None = None
    description: str = ""

    def problems(self) -> list[str]:
        out = check_name(self.name, "webhook")
        if not re.match(r"^https?://", self.url):
            out.append("url starts with http:// or https://")
        if not 1 <= self.max_attempts <= 10:
            out.append("max_attempts is between 1 and 10")
        if not self.events:
            out.append("events cannot be empty (use ['*'] for all)")
        if isinstance(self.secret, str) and len(self.secret) < 16:
            out.append("secret is at least 16 characters")
        return out
