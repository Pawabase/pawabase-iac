from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from ..core.base import Definition, check_name, plain
from .check import condition_problems


@dataclass
class Policy(Definition):
    """A named access rule that tables, buckets, routes and channels refer to.

        Policy("mine", P.owner())
        Policy("staff", P.role("admin") | P.role("support"))
        Policy("verified_adults", P.authenticated() & (P.auth.age >= 18) & P.aal("aal2"))
    """

    kind: ClassVar[str] = "policies"
    name: str
    condition: Any
    description: str = ""

    def problems(self) -> list[str]:
        return check_name(self.name, "policy") + condition_problems(plain(self.condition, resolve=False), "condition")
